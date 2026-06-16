"""The plan to tasks slicer.

The Process stage writes plan_json on a Project: workstreams, deliverables, subtasks, and
dependencies. That plan is descriptive; nothing here turns it into work the build engine can run. The
slicer does: it reads an approved project's plan_json and produces an ordered set of Task rows, each a
small buildable unit, carrying a sequence and a dependency relation so the orchestrator can walk them
in order.

The slicer is deterministic and idempotent. Each buildable unit gets a stable key derived from the
plan (its declared id, or its order and title), so re-slicing the same plan reconciles in place rather
than duplicating: a unit still in the plan updates its task, a unit dropped from the plan soft deletes
its task (never a hard delete), and nothing is created twice. Dependencies declared between units are
resolved to prerequisite task ids and stored on each task.

Each generated task inherits the project's agent_autonomy_default. The dial only ever tightens: if the
plan marks a unit higher risk, or the deterministic risk classifier flags its text (auth, payments,
migrations, deploy, secrets, or a destructive action), the task starts more conservative, never less.

A plan with no buildable units, or a malformed plan_json, is rejected cleanly so a caller can return a
clear error rather than silently producing an empty graph.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.autonomy import classify_risk, escalate, normalize_level
from app.models.base import utcnow
from app.models.inbox import InboxItem
from app.models.project import Project
from app.models.workspace import Task

# The marker that a task was generated from a plan. Stored in Task.source alongside the plan_unit_key
# link, so generated tasks are distinguishable from hand created ones.
PLAN_SOURCE = "plan"

# Risk words a plan unit may carry, mapped to the autonomy floor they impose. The floor only ever
# raises risk; a unit that names none of these inherits the project default unchanged.
_RISK_TO_LEVEL = {
    "low": "green",
    "normal": "green",
    "medium": "yellow",
    "med": "yellow",
    "elevated": "yellow",
    "high": "yellow",
    "critical": "red",
    "severe": "red",
    "dangerous": "red",
    # A unit may also state an autonomy level directly.
    "green": "green",
    "yellow": "yellow",
    "red": "red",
}

# The plan_json keys the slicer draws buildable units from, in order of preference. subtasks are the
# smallest buildable units; deliverables and then workstreams are the coarser fallbacks.
_UNIT_SOURCES = ("subtasks", "deliverables", "workstreams")


class SlicerError(Exception):
    """Raised when a plan cannot be sliced (missing, malformed, or with no buildable units)."""


@dataclass
class _Unit:
    """One buildable unit parsed from the plan, before it becomes a Task row."""

    key: str
    title: str
    sequence: int
    detail: str | None = None
    goal: str | None = None
    workstream: str | None = None
    risk_floor: str = "green"
    depends_on_tokens: list[str] = field(default_factory=list)
    depends_on_keys: list[str] = field(default_factory=list)


def _slug(text: str) -> str:
    """A short, stable slug for a unit title, used in its derived key."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return cleaned[:40] or "unit"


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _coerce_token_list(value: Any) -> list[str]:
    """Normalise a dependency reference (a scalar or a list) into a list of token strings."""
    if value in (None, "", [], {}):
        return []
    items = value if isinstance(value, list) else [value]
    tokens: list[str] = []
    for item in items:
        if isinstance(item, (str, int)):
            token = str(item).strip()
            if token:
                tokens.append(token)
    return tokens


def _risk_floor(*candidates: Any) -> str:
    """The autonomy floor a unit imposes from any risk or autonomy words it carries."""
    floor = "green"
    for candidate in candidates:
        word = _as_text(candidate).lower()
        if word in _RISK_TO_LEVEL:
            floor = escalate(floor, _RISK_TO_LEVEL[word])
    return floor


def _parse_units(plan: dict[str, Any]) -> list[_Unit]:
    """Parse the plan's buildable units, in order, from the first non empty unit source."""
    source_list: list[Any] = []
    for key in _UNIT_SOURCES:
        candidate = plan.get(key)
        if isinstance(candidate, list) and candidate:
            source_list = candidate
            break
    if not source_list:
        raise SlicerError(
            "plan has no buildable units (expected a non empty subtasks, deliverables, or "
            "workstreams list)"
        )

    units: list[_Unit] = []
    used_keys: set[str] = set()
    for index, entry in enumerate(source_list):
        unit = _parse_entry(entry, index)
        if unit is None:
            continue
        # Guarantee key uniqueness even if two units slug to the same string.
        base_key = unit.key
        suffix = 2
        while unit.key in used_keys:
            unit.key = f"{base_key}-{suffix}"
            suffix += 1
        used_keys.add(unit.key)
        units.append(unit)

    if not units:
        raise SlicerError("plan units could not be parsed into any buildable task")
    return units


def _parse_entry(entry: Any, index: int) -> _Unit | None:
    """Parse one plan entry (a string or an object) into a unit, or None when it is empty."""
    order = index + 1
    if isinstance(entry, str):
        title = entry.strip()
        if not title:
            return None
        return _Unit(key=f"u{order}-{_slug(title)}", title=title[:300], sequence=order)

    if isinstance(entry, dict):
        title = (
            _as_text(entry.get("title"))
            or _as_text(entry.get("name"))
            or _as_text(entry.get("summary"))
            or _as_text(entry.get("task"))
        )
        if not title:
            return None
        declared_id = _as_text(entry.get("id")) or _as_text(entry.get("key"))
        key = f"id-{_slug(declared_id)}" if declared_id else f"u{order}-{_slug(title)}"
        sequence = entry.get("sequence")
        if not isinstance(sequence, int):
            sequence = entry.get("order") if isinstance(entry.get("order"), int) else order
        depends = _coerce_token_list(
            entry.get("depends_on")
            if entry.get("depends_on") is not None
            else entry.get("after")
            if entry.get("after") is not None
            else entry.get("dependencies")
        )
        return _Unit(
            key=key,
            title=title[:300],
            sequence=sequence,
            detail=_as_text(entry.get("detail")) or _as_text(entry.get("description")) or None,
            goal=_as_text(entry.get("goal")) or _as_text(entry.get("goal_for_agent")) or None,
            workstream=_as_text(entry.get("workstream")) or None,
            risk_floor=_risk_floor(
                entry.get("risk"), entry.get("risk_level"), entry.get("autonomy")
            ),
            depends_on_tokens=depends,
        )
    return None


def _resolve_dependencies(plan: dict[str, Any], units: list[_Unit]) -> None:
    """Resolve every unit's dependency tokens (and any top level dependency edges) to unit keys.

    A token may name a unit by its declared id, its title, its key, or its 1 based order. Unresolved
    tokens and self references are dropped, so a dependency relation always points at a real unit.
    """
    by_id: dict[str, str] = {}
    by_title: dict[str, str] = {}
    by_order: dict[str, str] = {}
    by_key: dict[str, str] = {}
    for unit in units:
        by_key[unit.key] = unit.key
        by_title[unit.title.lower()] = unit.key
        by_order[str(unit.sequence)] = unit.key
        if unit.key.startswith("id-"):
            by_id[unit.key[3:]] = unit.key

    def resolve(token: str) -> str | None:
        token = token.strip()
        if not token:
            return None
        lowered = token.lower()
        return (
            by_key.get(token)
            or by_id.get(_slug(token))
            or by_title.get(lowered)
            or by_order.get(token)
        )

    # Top level dependency edges, when the plan declares them as objects.
    raw_edges = plan.get("dependencies")
    if isinstance(raw_edges, list):
        edges_by_unit: dict[str, list[str]] = {}
        for edge in raw_edges:
            if not isinstance(edge, dict):
                continue
            target = _as_text(edge.get("task")) or _as_text(edge.get("unit")) or _as_text(
                edge.get("from")
            )
            prereqs = _coerce_token_list(
                edge.get("depends_on")
                if edge.get("depends_on") is not None
                else edge.get("on")
                if edge.get("on") is not None
                else edge.get("to")
            )
            if target and prereqs:
                edges_by_unit.setdefault(target, []).extend(prereqs)
        for unit in units:
            for token in (
                edges_by_unit.get(unit.key, [])
                + edges_by_unit.get(unit.title, [])
                + edges_by_unit.get(str(unit.sequence), [])
            ):
                unit.depends_on_tokens.append(token)

    for unit in units:
        resolved: list[str] = []
        for token in unit.depends_on_tokens:
            target_key = resolve(token)
            if target_key and target_key != unit.key and target_key not in resolved:
                resolved.append(target_key)
        unit.depends_on_keys = resolved


def _owner_user_id(db: Session, project: Project) -> int | None:
    """The user a generated task belongs to: the owner of the project's source item, when there is
    one. An unlinked project yields None (a shared task), matching how the agents router gates reads."""
    if project.item_id is None:
        return None
    item = db.get(InboxItem, project.item_id)
    return item.user_id if item is not None else None


def _generated_tasks(db: Session, project: Project) -> list[Task]:
    """The project's live (not soft deleted) tasks that the slicer generated, by plan_unit_key."""
    return (
        db.query(Task)
        .filter(
            Task.project_id == project.id,
            Task.plan_unit_key.isnot(None),
            Task.deleted_at.is_(None),
        )
        .all()
    )


def slice_plan(db: Session, project: Project, *, proposed_by: str = "system") -> dict:
    """Slice a project's plan_json into an ordered, reconciled set of buildable Task rows.

    Reads the plan, parses its buildable units, and reconciles them against the tasks already
    generated for this project keyed by plan_unit_key: a unit still present updates its task in place,
    a new unit creates a task, and a unit dropped from the plan soft deletes its task. Dependencies are
    resolved to prerequisite task ids. Each task inherits the project autonomy default, escalated when
    the plan or the risk classifier marks the unit higher risk. Returns the task graph. Idempotent:
    re-slicing the same plan yields the same graph with no duplicates.
    """
    plan = project.plan_json
    if not isinstance(plan, dict) or not plan:
        raise SlicerError("project has no plan_json to slice")

    units = _parse_units(plan)
    _resolve_dependencies(plan, units)

    project_default = normalize_level(project.agent_autonomy_default)
    owner_id = _owner_user_id(db, project)
    existing_by_key = {t.plan_unit_key: t for t in _generated_tasks(db, project)}
    seen_keys: set[str] = set()

    for unit in units:
        seen_keys.add(unit.key)
        classifier = classify_risk(
            text=" ".join(p for p in (unit.title, unit.detail, unit.goal) if p)
        )
        autonomy = escalate(project_default, unit.risk_floor, classifier.level)
        task = existing_by_key.get(unit.key)
        if task is None:
            task = Task(
                user_id=owner_id,
                project_id=project.id,
                title=unit.title,
                detail=unit.detail,
                goal_for_agent=unit.goal,
                status="todo",
                source=PLAN_SOURCE,
                autonomy=autonomy,
                sequence=unit.sequence,
                position=unit.sequence,
                plan_unit_key=unit.key,
                depends_on=[],
            )
            db.add(task)
        else:
            task.title = unit.title
            task.detail = unit.detail
            task.goal_for_agent = unit.goal
            task.sequence = unit.sequence
            # Reconcile autonomy upward only, so a re-slice never relaxes a task already made more
            # conservative (by the plan, the classifier, or a person).
            task.autonomy = escalate(task.autonomy, autonomy)

    # A unit dropped from the plan soft deletes its task: the row stays, recoverable, and falls out of
    # the graph and the default task lists. Nothing is hard deleted.
    for key, task in existing_by_key.items():
        if key not in seen_keys:
            task.deleted_at = utcnow()

    db.commit()

    # Second pass: now that every kept task has an id, resolve dependency keys to prerequisite ids.
    key_to_id = {t.plan_unit_key: t.id for t in _generated_tasks(db, project)}
    for unit in units:
        task_id = key_to_id.get(unit.key)
        if task_id is None:
            continue
        task = db.get(Task, task_id)
        task.depends_on = [
            key_to_id[dep_key] for dep_key in unit.depends_on_keys if dep_key in key_to_id
        ]
    db.commit()

    return task_graph(db, project)


def task_graph(db: Session, project: Project) -> dict:
    """The current build task graph for a project: its generated tasks, ordered, with dependencies.

    Ordered by sequence then id so the orchestrator can walk it. Soft deleted tasks are excluded.
    plan_present reports whether the project carries a plan_json to slice at all.
    """
    tasks = _generated_tasks(db, project)
    tasks.sort(key=lambda t: ((t.sequence if t.sequence is not None else 1_000_000), t.id))
    nodes = [
        {
            "id": t.id,
            "title": t.title,
            "detail": t.detail,
            "goal_for_agent": t.goal_for_agent,
            "status": t.status,
            "autonomy": t.autonomy,
            "priority": t.priority,
            "sequence": t.sequence,
            "depends_on": list(t.depends_on or []),
            "plan_unit_key": t.plan_unit_key,
            "run_id": t.run_id,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }
        for t in tasks
    ]
    return {
        "project_id": project.id,
        "plan_present": bool(isinstance(project.plan_json, dict) and project.plan_json),
        "count": len(nodes),
        "tasks": nodes,
    }
