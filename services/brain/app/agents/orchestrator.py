"""The orchestrator loop: walk a sliced project's task graph and dispatch build runs in order.

Given a sliced, approved project, the orchestrator walks the task graph in dependency order. For each
ready task (all its prerequisites satisfied) it dispatches a build run through the existing
build_engine start_build_run on the in process worker. Disposition follows the autonomy dial exactly,
never bypassing it:

  - A green task auto advances: start_build_run runs the agent, the deterministic classifier confirms
    green, the run merges through the executor, and the loop continues to that task's dependents.
  - A yellow or red task parks at the Human Gate. The loop pauses that branch (its dependents stay
    blocked) and moves on to other ready branches, until a person resolves the gate.

The orchestrator never bypasses classify_risk and never force merges: every merge goes through the
same gate_decision the single run path uses. The project kill switch halts the whole loop immediately
and refuses new dispatch until released. Two bounds keep a loop from running unbounded: a run cap (the
most dispatches one loop may make) and a wall-clock budget in seconds. On hitting either, the loop
pauses and reports. Every dispatch, gate decision, and pause is recorded on the project's PMRun.state
and on each run.plan, so the loop is fully auditable.

The whole loop is gated behind NEXA_ENABLE_ORCHESTRATOR, which defaults false: until it is on, the
loop cannot dispatch a real agent. See docs/ARCHITECTURE.md for the go-live preconditions.
"""

import logging
import time

from sqlalchemy.orm import Session

from app.agents.build_engine import (
    BuildEngineError,
    KillSwitchEngagedError,
    start_build_run,
)
from app.agents.executor import PHASE_MERGED
from app.agents.slicer import task_graph
from app.audit import audit_orchestrator
from app.models.base import utcnow
from app.models.project import PMRun, Project
from app.models.workspace import Task
from app.settings import get_settings

logger = logging.getLogger(__name__)

# A task counts as satisfied for its dependents once its change has merged (green auto advance) or a
# human has approved it: both land the task at review, and done is the terminal human state.
_SATISFIED_STATUSES = ("review", "done")

# The stage a project must reach before the orchestrator will run it. Approval is the gate here, not
# at slice time: a plan can be sliced into tasks for inspection before the project is approved to run.
_APPROVED_STAGE = "approved"

# PMRun.status values the orchestrator uses for the loop record.
PM_ACTIVE = "active"
PM_PAUSED = "paused"
PM_COMPLETED = "completed"
PM_BLOCKED = "blocked"
PM_HALTED = "halted"

# How many audit entries of each kind to keep on PMRun.state, newest last, so the record cannot grow
# without bound across many loop invocations.
_AUDIT_CAP = 500


class OrchestratorError(Exception):
    """Base error for an orchestration request that cannot run."""


class OrchestratorDisabledError(OrchestratorError):
    """Raised when the orchestrator feature flag is off, so no real agent may be dispatched."""


class OrchestratorNotApprovedError(OrchestratorError):
    """Raised when the project has not been approved to run."""


class OrchestratorHaltedError(OrchestratorError):
    """Raised when the project kill switch is engaged, so new dispatch is refused."""


class OrchestratorPausedError(OrchestratorError):
    """Raised when the loop is paused and must be resumed before it can run again."""


def _get_or_create_pmrun(db: Session, project: Project) -> PMRun:
    """The project's PMRun, the orchestration record. Reuses the most recent one, or creates it."""
    pm = (
        db.query(PMRun)
        .filter(PMRun.project_id == project.id)
        .order_by(PMRun.id.desc())
        .first()
    )
    if pm is None:
        pm = PMRun(project_id=project.id, status=PM_ACTIVE, state={})
        db.add(pm)
        db.commit()
        db.refresh(pm)
    return pm


def _generated_tasks(db: Session, project: Project) -> list[Task]:
    """The project's live (not soft deleted) tasks the slicer generated, ordered for the walk."""
    tasks = (
        db.query(Task)
        .filter(
            Task.project_id == project.id,
            Task.plan_unit_key.isnot(None),
            Task.deleted_at.is_(None),
        )
        .all()
    )
    tasks.sort(key=lambda t: ((t.sequence if t.sequence is not None else 1_000_000), t.id))
    return tasks


def _ready_tasks(db: Session, project: Project, attempted: set[int]) -> list[Task]:
    """The tasks ready to dispatch: still todo, not yet attempted this loop, every prerequisite met.

    A prerequisite is met when the dependency task is satisfied (merged or approved). A task whose
    dependency is still pending or parked at a gate stays blocked, so a paused branch never advances.
    """
    tasks = _generated_tasks(db, project)
    satisfied = {t.id for t in tasks if t.status in _SATISFIED_STATUSES}
    ready: list[Task] = []
    for task in tasks:
        if task.status != "todo" or task.id in attempted:
            continue
        deps = list(task.depends_on or [])
        if all(dep_id in satisfied for dep_id in deps):
            ready.append(task)
    return ready


def _run_decision(run) -> dict:
    """The autonomy gate decision recorded on a run by start_build_run, or a safe default."""
    build = run.plan.get("build", {}) if isinstance(run.plan, dict) else {}
    decision = build.get("autonomy")
    return decision if isinstance(decision, dict) else {}


def _append(state: dict, key: str, entry: dict) -> None:
    """Append an audit entry under a capped list on the loop state."""
    log = list(state.get(key, []))
    log.append(entry)
    state[key] = log[-_AUDIT_CAP:]


def _pause_reason(run, decision: dict) -> str:
    """Why a dispatched task did not auto advance, for the audit trail."""
    if run.phase == "failed":
        return "run_failed"
    if decision.get("is_red"):
        return "red_gate"
    return "yellow_gate"


def orchestrate_project(
    db: Session,
    project: Project,
    *,
    run_cap: int | None = None,
    budget_seconds: int | None = None,
    proposed_by: str = "system",
) -> dict:
    """Run the orchestration loop for a project and return its state.

    Refused when the orchestrator flag is off, when the project is not approved, when the kill switch
    is engaged, or when the loop is paused. Walks the task graph dispatching ready tasks: green tasks
    auto advance and unlock their dependents; yellow and red tasks park at the gate and pause their
    branch. Stops on a drained graph, the run cap, the wall-clock budget, or the kill switch. The whole
    loop is recorded on the project's PMRun.state.
    """
    settings = get_settings()
    if not settings.nexa_enable_orchestrator:
        raise OrchestratorDisabledError(
            "the orchestrator is disabled (set NEXA_ENABLE_ORCHESTRATOR to enable it)"
        )
    if project.stage != _APPROVED_STAGE:
        raise OrchestratorNotApprovedError(
            f"project '{project.slug}' is not approved (stage is '{project.stage}')"
        )
    if project.agent_kill_switch:
        raise OrchestratorHaltedError(
            f"the kill switch is engaged for project '{project.slug}'; dispatch is refused"
        )

    pm = _get_or_create_pmrun(db, project)
    if pm.status == PM_PAUSED:
        raise OrchestratorPausedError(
            f"orchestration for project '{project.slug}' is paused; resume it before running"
        )

    cap = run_cap if run_cap is not None else settings.nexa_orchestrator_run_cap
    budget = (
        budget_seconds if budget_seconds is not None else settings.nexa_orchestrator_budget_seconds
    )

    state = dict(pm.state or {})
    state.setdefault("dispatches", [])
    state.setdefault("gate_decisions", [])
    state.setdefault("pauses", [])
    state["run_cap"] = cap
    state["budget_seconds"] = budget
    pm.status = PM_ACTIVE
    db.commit()

    attempted: set[int] = set()
    dispatched = 0
    stopped_reason: str | None = None
    started_at = time.monotonic()

    while True:
        if dispatched >= cap:
            stopped_reason = "run_cap"
            break
        if time.monotonic() - started_at >= budget:
            stopped_reason = "time_budget"
            break
        # Re-read the kill switch each turn so an engage mid-loop halts the whole loop immediately.
        db.refresh(project)
        if project.agent_kill_switch:
            stopped_reason = "kill_switch"
            _append(state, "pauses", {"reason": "kill_switch", "at": utcnow().isoformat()})
            break

        ready = _ready_tasks(db, project, attempted)
        if not ready:
            break

        task = ready[0]
        attempted.add(task.id)
        try:
            run = start_build_run(db, task=task, proposed_by=proposed_by)
        except KillSwitchEngagedError:
            stopped_reason = "kill_switch"
            _append(state, "pauses", {"reason": "kill_switch", "at": utcnow().isoformat()})
            break
        except BuildEngineError as exc:
            _append(
                state,
                "pauses",
                {"reason": "dispatch_error", "task_id": task.id, "detail": str(exc),
                 "at": utcnow().isoformat()},
            )
            stopped_reason = "dispatch_error"
            break

        dispatched += 1
        decision = _run_decision(run)
        now = utcnow().isoformat()
        merged = bool(decision.get("auto_advance")) and run.phase == PHASE_MERGED
        _append(
            state,
            "dispatches",
            {
                "task_id": task.id,
                "plan_unit_key": task.plan_unit_key,
                "run_id": run.id,
                "effective_level": decision.get("effective_level"),
                "auto_advance": bool(decision.get("auto_advance")),
                "phase": run.phase,
                "merged": merged,
                "at": now,
            },
        )
        _append(
            state,
            "gate_decisions",
            {
                "task_id": task.id,
                "run_id": run.id,
                "effective_level": decision.get("effective_level"),
                "auto_advance": bool(decision.get("auto_advance")),
                "reasons": decision.get("reasons", []),
                "at": now,
            },
        )
        if not merged:
            _append(
                state,
                "pauses",
                {"reason": _pause_reason(run, decision), "task_id": task.id, "run_id": run.id,
                 "at": now},
            )

    status = _final_status(db, project, stopped_reason)
    state["stopped_reason"] = stopped_reason
    state["runs_dispatched_last"] = dispatched
    state["runs_dispatched_total"] = int(state.get("runs_dispatched_total", 0)) + dispatched
    state["updated_at"] = utcnow().isoformat()
    pm.status = status
    pm.state = state
    db.commit()
    return orchestration_state(db, project)


def _final_status(db: Session, project: Project, stopped_reason: str | None) -> str:
    """The PMRun status the loop lands on, from how it stopped and whether the graph is complete."""
    tasks = _generated_tasks(db, project)
    all_satisfied = bool(tasks) and all(t.status in _SATISFIED_STATUSES for t in tasks)
    if all_satisfied:
        return PM_COMPLETED
    if stopped_reason == "kill_switch":
        return PM_HALTED
    if stopped_reason in ("run_cap", "time_budget"):
        return PM_PAUSED
    # Drained with work still pending: the loop is blocked waiting on human gates or a failed branch.
    return PM_BLOCKED


def pause_loop(
    db: Session, project: Project, *, reason: str = "manual", actor: str = "user"
) -> dict:
    """Pause the loop: the orchestrator refuses to run until it is resumed. Soft state only.

    reason records why the loop paused (manual from the endpoint, budget when a project budget is
    breached); the pause is recorded both on the loop state and as a governance audit event.
    """
    pm = _get_or_create_pmrun(db, project)
    pm.status = PM_PAUSED
    state = dict(pm.state or {})
    _append(state, "pauses", {"reason": reason, "at": utcnow().isoformat()})
    pm.state = state
    db.commit()
    audit_orchestrator(
        db, action="pause", actor=actor, project_id=project.id, reason=reason
    )
    return orchestration_state(db, project)


def resume_loop(db: Session, project: Project, *, actor: str = "user") -> dict:
    """Resume a paused loop so the next orchestrate call may run. Does not itself dispatch."""
    pm = _get_or_create_pmrun(db, project)
    if pm.status == PM_PAUSED:
        pm.status = PM_ACTIVE
        db.commit()
        audit_orchestrator(db, action="resume", actor=actor, project_id=project.id)
    return orchestration_state(db, project)


def orchestration_state(db: Session, project: Project) -> dict:
    """The loop's state and per task progress for a project: status, bounds, audit, and the graph."""
    settings = get_settings()
    pm = (
        db.query(PMRun)
        .filter(PMRun.project_id == project.id)
        .order_by(PMRun.id.desc())
        .first()
    )
    state = dict(pm.state or {}) if pm is not None else {}
    graph = task_graph(db, project)
    return {
        "project_id": project.id,
        "enabled": settings.nexa_enable_orchestrator,
        "approved": project.stage == _APPROVED_STAGE,
        "kill_switch_engaged": project.agent_kill_switch,
        "status": pm.status if pm is not None else "idle",
        "run_cap": state.get("run_cap"),
        "budget_seconds": state.get("budget_seconds"),
        "runs_dispatched": int(state.get("runs_dispatched_total", 0)),
        "stopped_reason": state.get("stopped_reason"),
        "dispatches": state.get("dispatches", []),
        "gate_decisions": state.get("gate_decisions", []),
        "pauses": state.get("pauses", []),
        "count": graph["count"],
        "tasks": graph["tasks"],
    }
