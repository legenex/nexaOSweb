"""Insights generation.

Derives insights from the Knowledge base and recent activity in two passes, following the
semantic key contract: the bulk key condenses the raw facts (extraction), and the
research_synthesis key writes the generative profile narrative (the final pass). The pattern
and idea insights are derived deterministically from real rows so the feed is grounded and
reproducible; the narrative is model written with a deterministic offline fallback, mirroring
the Dashboard brief. Every insight carries a confidence, a source, and a short reasoning
summary. A run supersedes the prior active batch so the latest batch is the cache.
"""

import logging
from collections import Counter
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.json_extract import synthesize_text
from app.models.base import utcnow
from app.models.inbox import ClassificationRecord, InboxItem
from app.models.insight import Insight, InsightRun
from app.models.knowledge import KnowledgeEntry
from app.models.project import Integration, Project
from app.models.workspace import JournalNote, Task
from app.project_modes import get_mode

logger = logging.getLogger(__name__)

# Semantic keys, resolved through the router so a model swap is a config change.
EXTRACTION_MODEL_KEY = "bulk"
SYNTHESIS_MODEL_KEY = "research_synthesis"

PERSONAL_SCOPES = ("personal", "general")
WORK_SCOPES = ("work", "development")

MAX_PERSONAL = 5
MAX_WORK = 5

TextSynthesizer = Callable[..., str | None]


def _owned_item_ids(db: Session, user_id: int) -> list[int]:
    return [row.id for row in db.query(InboxItem.id).filter(InboxItem.user_id == user_id).all()]


def _gather_context(db: Session, user_id: int) -> dict[str, Any]:
    """Collect the Knowledge base entries and recent activity that feed generation."""
    knowledge = (
        db.query(KnowledgeEntry)
        .filter(KnowledgeEntry.status == "active")
        .order_by(KnowledgeEntry.confidence.desc(), KnowledgeEntry.updated_at.desc())
        .all()
    )
    item_ids = _owned_item_ids(db, user_id)
    projects = (
        db.query(Project)
        .filter((Project.item_id.in_(item_ids)) | (Project.item_id.is_(None)))
        .order_by(Project.created_at.desc(), Project.id.desc())
        .all()
    )
    shape_counts: Counter[str] = Counter()
    if item_ids:
        for record in (
            db.query(ClassificationRecord.shape)
            .filter(ClassificationRecord.item_id.in_(item_ids))
            .all()
        ):
            shape_counts[record.shape] += 1

    unconverted = []
    linked_item_ids = {p.item_id for p in projects if p.item_id is not None}
    for item in (
        db.query(InboxItem)
        .filter(InboxItem.user_id == user_id, InboxItem.status != "archived")
        .order_by(InboxItem.created_at.desc(), InboxItem.id.desc())
        .all()
    ):
        if item.id not in linked_item_ids:
            unconverted.append(item)

    journal_count = (
        db.query(JournalNote).filter(JournalNote.user_id == user_id).count()
    )
    open_tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.status == "open", Task.deleted_at.is_(None))
        .count()
    )
    integrations = (
        db.query(Integration)
        .filter(Integration.user_id == user_id)
        .order_by(Integration.provider.asc())
        .all()
    )

    return {
        "knowledge": knowledge,
        "projects": projects,
        "shape_counts": shape_counts,
        "unconverted": unconverted,
        "journal_count": journal_count,
        "open_tasks": open_tasks,
        "integrations": integrations,
    }


def _facts_to_text(context: dict[str, Any]) -> str:
    knowledge = context["knowledge"]
    projects = context["projects"]
    shapes = context["shape_counts"]
    integrations = context["integrations"]
    lines = [
        "knowledge entries: "
        + (
            "; ".join(f"[{k.scope}/{k.kind}] {k.content}" for k in knowledge[:8]) or "none"
        ),
        "projects: "
        + (
            ", ".join(f"{p.name} ({p.mode}, {p.stage})" for p in projects[:8]) or "none"
        ),
        "capture shapes: "
        + (", ".join(f"{shape}:{count}" for shape, count in shapes.most_common()) or "none"),
        "unconverted captures: "
        + (", ".join(i.name for i in context["unconverted"][:6]) or "none"),
        f"journal notes: {context['journal_count']}",
        f"open tasks: {context['open_tasks']}",
        "connected integrations: "
        + (
            ", ".join(f"{i.provider}:{i.status}" for i in integrations) or "none"
        ),
    ]
    return "\n".join(lines)


def _mean_confidence(knowledge: list[KnowledgeEntry]) -> float:
    if not knowledge:
        return 0.6
    return round(sum(k.confidence for k in knowledge) / len(knowledge), 2)


def _ref(kind: str, obj: Any) -> dict[str, Any]:
    title = (
        getattr(obj, "content", None)
        or getattr(obj, "name", None)
        or getattr(obj, "provider", None)
        or ""
    )
    return {"type": kind, "id": obj.id, "title": str(title)[:120]}


def _personal_patterns(context: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in context["knowledge"]:
        if entry.scope in PERSONAL_SCOPES and entry.kind in ("preference", "pattern", "fact"):
            out.append(
                {
                    "category": "personal_pattern",
                    "title": entry.content[:120],
                    "body": entry.content,
                    "confidence": entry.confidence,
                    "source": "knowledge",
                    "reasoning": f"Derived from a {entry.kind} in your {entry.scope} knowledge.",
                    "source_refs": [_ref("knowledge", entry)],
                }
            )
        if len(out) >= MAX_PERSONAL - 1:
            break

    journal_count = context["journal_count"]
    if journal_count:
        confidence = round(min(0.9, 0.45 + journal_count * 0.05), 2)
        out.append(
            {
                "category": "personal_pattern",
                "title": "You reflect through regular journaling",
                "body": (
                    f"You have written {journal_count} journal "
                    f"{'note' if journal_count == 1 else 'notes'}, a steady reflection habit "
                    "that feeds the nightly consolidation."
                ),
                "confidence": confidence,
                "source": "activity",
                "reasoning": f"Based on {journal_count} journal notes in your workspace.",
                "source_refs": [],
            }
        )
    return out[:MAX_PERSONAL]


def _work_patterns(context: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in context["knowledge"]:
        if entry.scope in WORK_SCOPES:
            out.append(
                {
                    "category": "work_pattern",
                    "title": entry.content[:120],
                    "body": entry.content,
                    "confidence": entry.confidence,
                    "source": "knowledge",
                    "reasoning": f"Derived from a {entry.kind} in your {entry.scope} knowledge.",
                    "source_refs": [_ref("knowledge", entry)],
                }
            )
        if len(out) >= 2:
            break

    projects = context["projects"]
    if projects:
        mode_counts = Counter(p.mode for p in projects)
        top_mode, top_count = mode_counts.most_common(1)[0]
        share = top_count / len(projects)
        out.append(
            {
                "category": "work_pattern",
                "title": f"You gravitate toward {get_mode(top_mode).label} builds",
                "body": (
                    f"{top_count} of your {len(projects)} projects are "
                    f"{get_mode(top_mode).label} mode, your most common build type."
                ),
                "confidence": round(min(0.9, 0.4 + share * 0.5), 2),
                "source": "activity",
                "reasoning": f"{top_count} of {len(projects)} projects use the {top_mode} mode.",
                "source_refs": [_ref("project", p) for p in projects if p.mode == top_mode][:5],
            }
        )

    shapes = context["shape_counts"]
    if shapes:
        top_shape, top_n = shapes.most_common(1)[0]
        total = sum(shapes.values())
        share = top_n / total
        out.append(
            {
                "category": "work_pattern",
                "title": f"Most of your captures are {top_shape}-shaped",
                "body": (
                    f"{top_n} of {total} classified captures were {top_shape}, the shape your "
                    "intake leans toward."
                ),
                "confidence": round(min(0.9, 0.4 + share * 0.5), 2),
                "source": "activity",
                "reasoning": f"{top_n} of {total} captures classified as {top_shape}.",
                "source_refs": [],
            }
        )
    return out[:MAX_WORK]


def _profile_summary(
    context: dict[str, Any], digest: str, synthesize: TextSynthesizer
) -> dict[str, Any] | None:
    knowledge = context["knowledge"]
    projects = context["projects"]
    if not knowledge and not projects:
        return None

    body = synthesize(
        SYNTHESIS_MODEL_KEY,
        (
            "Write a two or three sentence generative profile of this person and how they "
            "work, grounded only in the facts. Direct and calm, no headings.\n\n"
            f"Facts:\n{digest}"
        ),
        system="You write concise, grounded profiles for a personal operating system.",
    )
    if not body:
        body = _offline_profile(context)

    return {
        "category": "profile_summary",
        "title": "Your generative profile",
        "body": body,
        "confidence": _mean_confidence(knowledge),
        "source": "knowledge+activity",
        "reasoning": (
            f"Synthesised from {len(knowledge)} knowledge entries and "
            f"{len(projects)} projects."
        ),
        "source_refs": [_ref("knowledge", k) for k in knowledge[:5]],
    }


def _offline_profile(context: dict[str, Any]) -> str:
    knowledge = context["knowledge"]
    projects = context["projects"]
    top = knowledge[0].content if knowledge else None
    parts = [
        f"You maintain {len(knowledge)} active knowledge "
        f"{'entry' if len(knowledge) == 1 else 'entries'} and "
        f"{len(projects)} {'project' if len(projects) == 1 else 'projects'}."
    ]
    if top:
        parts.append(f"A defining signal: {top}")
    if projects:
        modes = Counter(p.mode for p in projects).most_common(1)[0][0]
        parts.append(f"You lean toward {get_mode(modes).label.lower()} work.")
    return " ".join(parts)


def _innovation(context: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    knowledge = context["knowledge"]
    projects = context["projects"]
    unconverted = context["unconverted"]
    integrations = context["integrations"]

    # Project idea: from an unconverted capture, else from a knowledge fact.
    if unconverted:
        seed = unconverted[0]
        out.append(
            {
                "category": "innovation",
                "idea_kind": "project",
                "title": f"Turn '{seed.name}' into a project",
                "body": (
                    f"'{seed.name}' was captured but never promoted. It is a candidate to "
                    "shape into a build."
                ),
                "confidence": 0.6,
                "source": "activity",
                "reasoning": "An unconverted capture is the cheapest path to a new project.",
                "source_refs": [_ref("inbox", seed)],
            }
        )
    elif knowledge:
        seed = knowledge[0]
        out.append(
            {
                "category": "innovation",
                "idea_kind": "project",
                "title": f"Build on: {seed.content[:80]}",
                "body": f"Your knowledge base suggests a project around: {seed.content}",
                "confidence": round(seed.confidence * 0.8, 2),
                "source": "knowledge",
                "reasoning": "A high confidence knowledge entry is a strong project seed.",
                "source_refs": [_ref("knowledge", seed)],
            }
        )

    # Revenue idea: from a project carrying revenue potential, else from any active project.
    revenue_project = next(
        (p for p in projects if (p.workspace or {}).get("revenue_potential")), None
    )
    active_project = next((p for p in projects if p.stage in ("build", "live")), None)
    target = revenue_project or active_project
    if target:
        note = (target.workspace or {}).get("revenue_potential")
        out.append(
            {
                "category": "innovation",
                "idea_kind": "revenue",
                "title": f"Monetize {target.name}",
                "body": (
                    f"{target.name} is at stage {target.stage}. "
                    + (f"Noted revenue potential: {note}. " if note else "")
                    + "Define a paid tier or offer to capture value."
                ),
                "confidence": 0.62 if note else 0.5,
                "source": "activity",
                "reasoning": "An advancing project is the nearest revenue opportunity.",
                "source_refs": [_ref("project", target)],
            }
        )

    # Automation idea: from connected integrations.
    connected = [i for i in integrations if i.status == "connected"]
    if len(connected) >= 2:
        a, b = connected[0].provider, connected[1].provider
        out.append(
            {
                "category": "innovation",
                "idea_kind": "automation",
                "title": f"Automate a flow between {a} and {b}",
                "body": (
                    f"Both {a} and {b} are connected. Wire an automation that moves work "
                    "between them."
                ),
                "confidence": 0.6,
                "source": "activity",
                "reasoning": f"{a} and {b} are both connected and ready to chain.",
                "source_refs": [_ref("integration", i) for i in connected[:2]],
            }
        )
    elif len(connected) == 1:
        a = connected[0].provider
        out.append(
            {
                "category": "innovation",
                "idea_kind": "automation",
                "title": f"Automate a recurring {a} task",
                "body": f"{a} is connected. Identify one repetitive {a} task to automate first.",
                "confidence": 0.55,
                "source": "activity",
                "reasoning": f"{a} is connected and a candidate for a first automation.",
                "source_refs": [_ref("integration", connected[0])],
            }
        )
    return out


def generate_insights(
    db: Session,
    user_id: int,
    *,
    trigger: str = "lazy",
    synthesize: TextSynthesizer | None = None,
) -> InsightRun:
    """Run one generation pass and return the InsightRun. Supersedes the prior active batch."""
    synthesize = synthesize or synthesize_text

    run = InsightRun(
        user_id=user_id,
        status="running",
        trigger=trigger,
        extraction_model_key=EXTRACTION_MODEL_KEY,
        synthesis_model_key=SYNTHESIS_MODEL_KEY,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        context = _gather_context(db, user_id)
        facts = _facts_to_text(context)

        # Extraction pass on the bulk key. Condenses the facts; the digest seeds the final
        # pass. Falls back to the raw facts when no provider key is configured.
        digest = (
            synthesize(
                EXTRACTION_MODEL_KEY,
                f"Condense these facts into terse lines, keep every number:\n{facts}",
                system="You compress notes. Keep it factual and short.",
            )
            or facts
        )

        payloads: list[dict[str, Any]] = []
        payloads.extend(_personal_patterns(context))
        payloads.extend(_work_patterns(context))
        profile = _profile_summary(context, digest, synthesize)
        if profile is not None:
            payloads.append(profile)
        payloads.extend(_innovation(context))

        # Supersede the prior active batch for this user so the new run is the cache.
        (
            db.query(Insight)
            .filter(Insight.user_id == user_id, Insight.status == "active")
            .update({Insight.status: "superseded"}, synchronize_session=False)
        )

        for payload in payloads:
            db.add(
                Insight(
                    run_id=run.id,
                    user_id=user_id,
                    category=payload["category"],
                    idea_kind=payload.get("idea_kind"),
                    title=payload["title"],
                    body=payload.get("body", ""),
                    confidence=max(0.0, min(1.0, float(payload.get("confidence", 0.5)))),
                    source=payload.get("source", "activity"),
                    reasoning=payload.get("reasoning", ""),
                    source_refs=payload.get("source_refs", []),
                    status="active",
                )
            )

        run.insights_created = len(payloads)
        run.status = "completed"
        run.finished_at = utcnow()
        db.commit()
        db.refresh(run)
        return run
    except Exception:
        db.rollback()
        run.status = "failed"
        run.finished_at = utcnow()
        db.commit()
        raise


def latest_run(db: Session, user_id: int) -> InsightRun | None:
    return (
        db.query(InsightRun)
        .filter(
            InsightRun.user_id == user_id,
            InsightRun.status == "completed",
        )
        .order_by(InsightRun.created_at.desc(), InsightRun.id.desc())
        .first()
    )
