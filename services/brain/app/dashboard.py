"""Dashboard aggregation and the time aware brief.

build_summary assembles the Command Radar state with counts and short lists. build_brief
writes a morning or evening narrative from the same sources, pre summarising with the bulk
key and writing the final text with research_synthesis. Both are read only. When no provider
key is set the brief falls back to a deterministic offline rendering so the Dashboard works
on a fresh checkout.
"""

from collections import Counter
from datetime import datetime

from sqlalchemy.orm import Session

from app.json_extract import synthesize_text
from app.models.dreaming import DreamRun
from app.models.inbox import ClassificationRecord, InboxItem
from app.models.knowledge import KnowledgeEntry
from app.models.project import Integration, Project
from app.models.user import User
from app.models.workspace import Task
from app.router.model_router import get_router
from app.schemas.dashboard import (
    BrainStatus,
    BriefMode,
    ConnectorHealth,
    DashboardSummary,
    ItemBrief,
    ModelUsage,
    Opportunity,
    ProjectBrief,
    ResearchFinding,
    TaskBrief,
)
from app.settings import get_settings

LIST_LIMIT = 5

# Semantic keys, resolved through the router so a model swap is a config change.
PRESUMMARISE_KEY = "bulk"
FINAL_BRIEF_KEY = "research_synthesis"

ACTIVE_STAGES = ("build", "live")
AWAITING_STAGE = "clarify"


def _owned_item_ids(db: Session, user: User) -> list[int]:
    return [row.id for row in db.query(InboxItem.id).filter(InboxItem.user_id == user.id).all()]


def _owned_projects(db: Session, user: User) -> list[Project]:
    item_ids = _owned_item_ids(db, user)
    return (
        db.query(Project)
        .filter((Project.item_id.in_(item_ids)) | (Project.item_id.is_(None)))
        .order_by(Project.created_at.desc(), Project.id.desc())
        .all()
    )


def _latest_classification(db: Session, item_id: int) -> ClassificationRecord | None:
    return (
        db.query(ClassificationRecord)
        .filter(ClassificationRecord.item_id == item_id)
        .order_by(ClassificationRecord.created_at.desc(), ClassificationRecord.id.desc())
        .first()
    )


def _research_findings(db: Session, user: User, projects: list[Project]) -> list[ResearchFinding]:
    """Classified captures that have not yet become a project: ready to convert."""
    linked_item_ids = {p.item_id for p in projects if p.item_id is not None}
    findings: list[ResearchFinding] = []
    items = (
        db.query(InboxItem)
        .filter(InboxItem.user_id == user.id, InboxItem.status != "archived")
        .order_by(InboxItem.created_at.desc(), InboxItem.id.desc())
        .all()
    )
    for item in items:
        if item.id in linked_item_ids:
            continue
        record = _latest_classification(db, item.id)
        if record is None:
            continue
        findings.append(
            ResearchFinding(
                id=item.id, name=item.name, shape=record.shape, confidence=record.confidence
            )
        )
    return findings


def _model_usage(db: Session, user: User) -> list[ModelUsage]:
    router = get_router()
    counter: Counter[str] = Counter()

    item_ids = _owned_item_ids(db, user)
    if item_ids:
        for record in (
            db.query(ClassificationRecord.recommended_model_key)
            .filter(ClassificationRecord.item_id.in_(item_ids))
            .all()
        ):
            counter[record.recommended_model_key] += 1

    for run in db.query(DreamRun.model_key).all():
        counter[run.model_key] += 1

    usage: list[ModelUsage] = []
    for key, count in counter.most_common():
        try:
            model_id = router.model_for(key)
        except KeyError:
            model_id = "unmapped"
        usage.append(ModelUsage(model_key=key, model_id=model_id, count=count))
    return usage


def _top_opportunity(
    awaiting: list[Project], findings: list[ResearchFinding], active: list[Project]
) -> Opportunity | None:
    if awaiting:
        project = awaiting[0]
        return Opportunity(
            title=f"Approve {project.name}",
            detail="A build is at the human gate and ready for your decision.",
            score=0.9,
        )
    if findings:
        top = max(findings, key=lambda f: f.confidence)
        return Opportunity(
            title=f"Convert {top.name}",
            detail=f"A {top.shape} finding is ready to turn into a project.",
            score=top.confidence,
        )
    if active:
        project = active[0]
        return Opportunity(
            title=f"Advance {project.name}",
            detail="Move the most recent active project one step forward.",
            score=0.5,
        )
    return None


def _project_brief(project: Project) -> ProjectBrief:
    return ProjectBrief(
        id=project.id,
        name=project.name,
        stage=project.stage,
        build_destination=project.build_destination,
    )


def _last_dream(db: Session) -> DreamRun | None:
    return (
        db.query(DreamRun)
        .order_by(DreamRun.created_at.desc(), DreamRun.id.desc())
        .first()
    )


def build_summary(db: Session, user: User, *, version: str) -> DashboardSummary:
    settings = get_settings()
    projects = _owned_projects(db, user)
    active = [p for p in projects if p.stage in ACTIVE_STAGES]
    awaiting = [p for p in projects if p.stage == AWAITING_STAGE]
    findings = _research_findings(db, user, projects)

    open_tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.status == "open", Task.deleted_at.is_(None))
        .order_by(Task.created_at.desc(), Task.id.desc())
        .all()
    )
    recent_items = (
        db.query(InboxItem)
        .filter(InboxItem.user_id == user.id)
        .order_by(InboxItem.created_at.desc(), InboxItem.id.desc())
        .limit(LIST_LIMIT)
        .all()
    )
    connectors = (
        db.query(Integration)
        .filter(Integration.user_id == user.id)
        .order_by(Integration.provider.asc())
        .all()
    )
    last_dream = _last_dream(db)

    return DashboardSummary(
        active_projects=[_project_brief(p) for p in active[:LIST_LIMIT]],
        active_projects_count=len(active),
        builds_awaiting_approval=[_project_brief(p) for p in awaiting[:LIST_LIMIT]],
        builds_awaiting_approval_count=len(awaiting),
        research_ready=findings[:LIST_LIMIT],
        research_ready_count=len(findings),
        suggested_tasks=[
            TaskBrief(id=t.id, title=t.title, status=t.status, project_id=t.project_id)
            for t in open_tasks[:LIST_LIMIT]
        ],
        suggested_tasks_count=len(open_tasks),
        top_opportunity=_top_opportunity(awaiting, findings, active),
        recent_uploads=[
            ItemBrief(id=i.id, name=i.name, source=i.source, created_at=i.created_at)
            for i in recent_items
        ],
        connector_health=[
            ConnectorHealth(provider=c.provider, status=c.status) for c in connectors
        ],
        model_usage=_model_usage(db, user),
        brain=BrainStatus(
            status="ok",
            version=version,
            database_connected=True,
            dreaming_enabled=settings.dreaming_enabled,
            sweep_enabled=settings.classify_sweep_enabled,
            last_dream_at=last_dream.created_at if last_dream else None,
        ),
    )


# Brief generation. The facts dict is the single source the model and the offline renderer
# both read, so the two stay consistent.


def _gather_facts(db: Session, user: User) -> dict:
    projects = _owned_projects(db, user)
    active = [p for p in projects if p.stage in ACTIVE_STAGES]
    awaiting = [p for p in projects if p.stage == AWAITING_STAGE]
    findings = _research_findings(db, user, projects)
    open_tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.status == "open", Task.deleted_at.is_(None))
        .order_by(Task.created_at.desc())
        .all()
    )
    accepted = (
        db.query(KnowledgeEntry)
        .filter(KnowledgeEntry.status == "active")
        .order_by(KnowledgeEntry.updated_at.desc(), KnowledgeEntry.id.desc())
        .limit(3)
        .all()
    )
    last_dream = _last_dream(db)

    return {
        "active": [p.name for p in active],
        "awaiting": [p.name for p in awaiting],
        "findings": [f.name for f in findings],
        "tasks": [t.title for t in open_tasks],
        "knowledge": [k.content for k in accepted],
        "last_dream": last_dream,
        "opportunity": _top_opportunity(awaiting, findings, active),
    }


def _facts_to_text(facts: dict) -> str:
    last_dream: DreamRun | None = facts["last_dream"]
    dream_line = (
        f"last dreaming run: {last_dream.candidates_created} candidates"
        if last_dream
        else "last dreaming run: none yet"
    )
    opportunity: Opportunity | None = facts["opportunity"]
    lines = [
        f"active projects: {', '.join(facts['active']) or 'none'}",
        f"builds awaiting approval: {', '.join(facts['awaiting']) or 'none'}",
        f"research findings ready to convert: {', '.join(facts['findings']) or 'none'}",
        f"open tasks: {', '.join(facts['tasks']) or 'none'}",
        f"latest accepted knowledge: {'; '.join(facts['knowledge']) or 'none'}",
        dream_line,
        f"top opportunity: {opportunity.title if opportunity else 'none'}",
    ]
    return "\n".join(lines)


def _presummarise(facts: dict) -> str:
    raw = _facts_to_text(facts)
    summary = synthesize_text(
        PRESUMMARISE_KEY,
        f"Condense these dashboard facts into terse lines, keeping every number:\n{raw}",
        system="You compress notes. Keep it factual and short.",
    )
    return summary or raw


def _brief_prompt(mode: BriefMode, digest: str) -> str:
    intent = (
        "Set the day: lead with the single most important focus, then list what to move."
        if mode == "morning"
        else "Review the day, note what progressed, then set up tomorrow's focus."
    )
    return (
        f"Write a short {mode} brief for a personal operating system dashboard. {intent} "
        "Two or three sentences, direct and calm, no headings, no markdown.\n\n"
        f"Facts:\n{digest}"
    )


def _offline_brief(mode: BriefMode, facts: dict, today: str) -> str:
    active = len(facts["active"])
    awaiting = len(facts["awaiting"])
    findings = len(facts["findings"])
    tasks = len(facts["tasks"])
    opportunity: Opportunity | None = facts["opportunity"]
    last_dream: DreamRun | None = facts["last_dream"]
    opp = opportunity.title if opportunity else "keep the pipeline moving"
    dream = (
        f"The last dreaming run surfaced {last_dream.candidates_created} memory candidates to review."
        if last_dream
        else "No dreaming run has surfaced candidates yet."
    )

    if mode == "morning":
        return (
            f"Good morning. Today, {today}, you have {active} active "
            f"{'project' if active == 1 else 'projects'}, {awaiting} "
            f"{'build' if awaiting == 1 else 'builds'} awaiting approval, {findings} research "
            f"{'finding' if findings == 1 else 'findings'} ready to convert, and {tasks} open "
            f"{'task' if tasks == 1 else 'tasks'}. Start with: {opp}. {dream}"
        )
    return (
        f"Good evening. Reviewing {today}: {active} active "
        f"{'project' if active == 1 else 'projects'}, {awaiting} "
        f"{'build' if awaiting == 1 else 'builds'} still awaiting approval, and {tasks} open "
        f"{'task' if tasks == 1 else 'tasks'} remaining. {dream} For tomorrow, lead with: {opp}."
    )


def build_brief(db: Session, user: User, mode: BriefMode, *, today: str) -> str:
    facts = _gather_facts(db, user)
    digest = _presummarise(facts)
    text = synthesize_text(
        FINAL_BRIEF_KEY,
        _brief_prompt(mode, digest),
        system="You are a focused chief of staff writing a daily brief.",
    )
    return text or _offline_brief(mode, facts, today)
