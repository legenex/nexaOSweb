"""Focus: the decide layer's read only operator view and explainable ranking.

Focus reads the live tables (Project, Task, BuildLogEntry, MemoryCandidate, PMRun, ResearchRun,
and the agent runtime AgentRun and AgentStep) through the same ownership scoping the Dashboard
uses, and derives two outputs. Neither writes anything.

The operator view answers "what needs me right now" as five queries: approvals waiting, stale
projects, blocked work, tasks safe to complete, and the recommended next actions (the head of the
ranked list). The ranked list scores every candidate action by four explainable factors (age,
risk, blocked, autonomy eligibility) and returns, for each, the reason it sits where it does.

The stale threshold is fixed at 7 days. A higher autonomy level is never assumed: a gated step
that is fully safe-set is marked autonomy eligible (an agent could take it off the user if autonomy
were raised), so it weighs less on the user, and the reason says so.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.dashboard import ACTIVE_STAGES, AWAITING_STAGE, _owned_projects
from app.gates import is_safe_set, materially_affects_outcome
from app.models.base import utcnow
from app.models.dreaming import MemoryCandidate
from app.models.project import BuildLogEntry, PMRun, Project
from app.models.research import ResearchRun
from app.models.runtime import AgentRun, AgentStep
from app.models.user import User
from app.models.workspace import Task
from app.runtime import (
    ACTIVE_RUN_STATUSES,
    RUN_BLOCKED,
    RUN_FAILED,
    RUN_WAITING_APPROVAL,
    WAITING_APPROVAL,
)
from app.schemas.focus import (
    FocusFactors,
    FocusItem,
    OperatorView,
    RankedAction,
    RankedActions,
    SourceRef,
)

# A project is stale after this many days without progress. Fixed, by the plan.
STALE_DAYS = 7
# How many ranked actions the operator view recommends.
RECOMMENDED_LIMIT = 5

# The deterministic score backbone. Age is capped so a very old low-value item cannot drown out a
# fresh high-risk one. Blocked work earns a bonus because it holds up other work; an autonomy
# eligible action earns a discount because an agent could take it off the user.
_RISK_WEIGHT = {"low": 5.0, "medium": 15.0, "high": 30.0}
_AGE_CAP = 30
_BLOCKED_BONUS = 25.0
_AUTONOMY_DISCOUNT = 10.0


@dataclass
class _Candidate:
    kind: str
    bucket: str  # approvals | stale | blocked | safe_task
    title: str
    detail: str
    source_type: str
    source_id: int | None
    age_days: int
    risk: str
    blocked: bool
    autonomy_eligible: bool


def _age_days(moment: datetime | None) -> int:
    if moment is None:
        return 0
    # SQLite can hand back a naive datetime; treat a missing tzinfo as UTC so the subtraction works.
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max(0, (utcnow() - moment).days)


def _is_deleted(project: Project) -> bool:
    # Mirrors the Projects router: a build project flags deleted in its workspace blob, a research
    # project in research_config. Either hides it from Focus.
    return bool((project.workspace or {}).get("deleted")) or bool(
        (project.research_config or {}).get("deleted")
    )


def _owned_runs(db: Session, owned_ids: set[int]) -> list[AgentRun]:
    # A run with no project is a system run, visible to the authenticated user, exactly as the
    # runtime router scopes it. A run with a project is visible when that project is owned.
    runs = db.query(AgentRun).order_by(AgentRun.updated_at.desc(), AgentRun.id.desc()).all()
    return [r for r in runs if r.project_id is None or r.project_id in owned_ids]


def _run_where(run: AgentRun, by_id: dict[int, Project]) -> str:
    if run.project_id is not None and run.project_id in by_id:
        return f" ({by_id[run.project_id].name})"
    return ""


def _waiting_steps(db: Session, run_id: int) -> list[AgentStep]:
    return (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run_id, AgentStep.status == WAITING_APPROVAL)
        .all()
    )


def _candidates(db: Session, user: User) -> list[_Candidate]:
    projects = [p for p in _owned_projects(db, user) if not _is_deleted(p)]
    owned_ids = {p.id for p in projects}
    by_id = {p.id: p for p in projects}
    out: list[_Candidate] = []

    runs = _owned_runs(db, owned_ids)
    # A project with a run in flight is progressing, so it is not stale even if its row is old.
    active_run_project_ids = {
        r.project_id
        for r in runs
        if r.status in ACTIVE_RUN_STATUSES and r.project_id is not None
    }
    active_pm_project_ids = {
        pm.project_id
        for pm in db.query(PMRun).filter(PMRun.status == "active").all()
        if pm.project_id in owned_ids
    }

    # --- builds at the human gate (approvals) ---
    for p in projects:
        if p.stage == AWAITING_STAGE:
            out.append(
                _Candidate(
                    kind="approve_build",
                    bucket="approvals",
                    title=f"Approve build: {p.name}",
                    detail="A build is at the human gate, waiting for your decision.",
                    source_type="project",
                    source_id=p.id,
                    age_days=_age_days(p.updated_at),
                    risk="high",
                    blocked=False,
                    autonomy_eligible=False,
                )
            )

    # --- stale projects (active but not progressing) ---
    for p in projects:
        if p.stage in ACTIVE_STAGES and p.id not in active_run_project_ids:
            age = _age_days(p.updated_at)
            if age >= STALE_DAYS:
                managed = p.id in active_pm_project_ids
                detail = (
                    f"No progress in {age} days despite an active project manager run."
                    if managed
                    else f"No progress in {age} days."
                )
                out.append(
                    _Candidate(
                        kind="advance_project",
                        bucket="stale",
                        title=f"Advance {p.name}",
                        detail=detail,
                        source_type="project",
                        source_id=p.id,
                        age_days=age,
                        risk="medium",
                        blocked=False,
                        autonomy_eligible=False,
                    )
                )

    # --- agent runs: approvals, blocks, and failures ---
    for r in runs:
        where = _run_where(r, by_id)
        if r.status == RUN_WAITING_APPROVAL:
            waiting = _waiting_steps(db, r.id)
            all_safe = bool(waiting) and all(is_safe_set(s.payload) for s in waiting)
            materially = any(materially_affects_outcome(s.payload) for s in waiting)
            out.append(
                _Candidate(
                    kind="approve_run",
                    bucket="approvals",
                    title=f"Approve run #{r.id}{where}",
                    detail="An agent run is waiting at an approval gate.",
                    source_type="run",
                    source_id=r.id,
                    age_days=_age_days(r.updated_at),
                    # A fully safe-set gate is low risk and could be delegated; anything that
                    # materially affects the outcome is a high-risk human decision.
                    risk="high" if materially else "low",
                    blocked=False,
                    autonomy_eligible=all_safe,
                )
            )
        elif r.status == RUN_BLOCKED:
            out.append(
                _Candidate(
                    kind="unblock_run",
                    bucket="blocked",
                    title=f"Unblock run #{r.id}{where}",
                    detail="An agent run is blocked and cannot proceed.",
                    source_type="run",
                    source_id=r.id,
                    age_days=_age_days(r.updated_at),
                    risk="high",
                    blocked=True,
                    autonomy_eligible=False,
                )
            )
        elif r.status == RUN_FAILED:
            out.append(
                _Candidate(
                    kind="fix_run",
                    bucket="blocked",
                    title=f"Fix failed run #{r.id}{where}",
                    detail="An agent run failed and needs a correction.",
                    source_type="run",
                    source_id=r.id,
                    age_days=_age_days(r.updated_at),
                    risk="high",
                    blocked=True,
                    autonomy_eligible=False,
                )
            )

    # --- tasks: blocked, and safe to complete ---
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.deleted_at.is_(None))
        .order_by(Task.created_at.desc(), Task.id.desc())
        .all()
    )
    for t in tasks:
        if t.status == "blocked":
            out.append(
                _Candidate(
                    kind="unblock_task",
                    bucket="blocked",
                    title=f"Unblock task: {t.title}",
                    detail="A task is blocked.",
                    source_type="task",
                    source_id=t.id,
                    age_days=_age_days(t.updated_at or t.created_at),
                    risk="medium",
                    blocked=True,
                    autonomy_eligible=False,
                )
            )
        elif t.status in ("open", "in_progress"):
            out.append(
                _Candidate(
                    kind="complete_task",
                    bucket="safe_task",
                    title=f"Complete: {t.title}",
                    detail="An actionable task you can finish.",
                    source_type="task",
                    source_id=t.id,
                    age_days=_age_days(t.created_at),
                    risk="low",
                    blocked=False,
                    autonomy_eligible=False,
                )
            )

    # --- pending memory candidates, aggregated into one approval ---
    pending = db.query(MemoryCandidate).filter(MemoryCandidate.status == "pending").all()
    if pending:
        oldest = max(_age_days(c.created_at) for c in pending)
        plural = "s" if len(pending) != 1 else ""
        out.append(
            _Candidate(
                kind="review_memory",
                bucket="approvals",
                title=f"Review {len(pending)} memory candidate{plural}",
                detail=(
                    "Dreaming surfaced candidates awaiting your approval before they enter "
                    "Knowledge."
                ),
                source_type="dreaming",
                source_id=None,
                age_days=oldest,
                risk="low",
                blocked=False,
                autonomy_eligible=False,
            )
        )

    # --- proposed build edits (approvals) ---
    proposed = db.query(BuildLogEntry).filter(BuildLogEntry.status == "proposed").all()
    for e in proposed:
        if e.project_id in owned_ids:
            label = e.summary or e.file_path or "a file edit"
            out.append(
                _Candidate(
                    kind="review_edit",
                    bucket="approvals",
                    title=f"Review edit: {label}",
                    detail="A proposed file edit is waiting to be applied.",
                    source_type="project",
                    source_id=e.project_id,
                    age_days=_age_days(e.created_at),
                    risk="medium",
                    blocked=False,
                    autonomy_eligible=False,
                )
            )

    # --- failed research runs (blocked) ---
    failed_research = db.query(ResearchRun).filter(ResearchRun.status == "failed").all()
    for rr in failed_research:
        if rr.project_id in owned_ids:
            out.append(
                _Candidate(
                    kind="review_research",
                    bucket="blocked",
                    title=f"Review failed research run #{rr.id}",
                    detail="A research run failed and its output is incomplete.",
                    source_type="project",
                    source_id=rr.project_id,
                    age_days=_age_days(rr.finished_at or rr.created_at),
                    risk="medium",
                    blocked=True,
                    autonomy_eligible=False,
                )
            )

    return out


def _score(c: _Candidate) -> float:
    score = float(min(c.age_days, _AGE_CAP))
    score += _RISK_WEIGHT.get(c.risk, 0.0)
    if c.blocked:
        score += _BLOCKED_BONUS
    if c.autonomy_eligible:
        score -= _AUTONOMY_DISCOUNT
    return round(score, 2)


def _reason(c: _Candidate, score: float) -> str:
    if c.age_days >= STALE_DAYS:
        age_part = f"waiting {c.age_days} days"
    elif c.age_days > 0:
        age_part = f"{c.age_days} day{'s' if c.age_days != 1 else ''} old"
    else:
        age_part = "new today"
    parts = [age_part, f"{c.risk} risk"]
    if c.blocked:
        parts.append("blocked, so it holds up other work")
    if c.autonomy_eligible:
        parts.append("eligible for autonomous handling, so an agent could take it off you")
    else:
        parts.append("needs your decision")
    return f"Ranked at {score:g}: {'; '.join(parts)}."


def _ranked(candidates: list[_Candidate]) -> list[RankedAction]:
    scored = [(c, _score(c)) for c in candidates]
    # Highest score first; ties broken by age, then a stable source key, so the order is
    # deterministic for the same data.
    scored.sort(
        key=lambda cs: (
            -cs[1],
            -cs[0].age_days,
            cs[0].source_type,
            cs[0].source_id or 0,
            cs[0].kind,
        )
    )
    actions: list[RankedAction] = []
    for rank, (c, score) in enumerate(scored, start=1):
        actions.append(
            RankedAction(
                rank=rank,
                kind=c.kind,
                title=c.title,
                detail=c.detail,
                source=SourceRef(type=c.source_type, id=c.source_id),
                score=score,
                reason=_reason(c, score),
                factors=FocusFactors(
                    age_days=c.age_days,
                    risk=c.risk,
                    blocked=c.blocked,
                    autonomy_eligible=c.autonomy_eligible,
                ),
            )
        )
    return actions


def _item(c: _Candidate) -> FocusItem:
    return FocusItem(
        kind=c.kind,
        title=c.title,
        detail=c.detail,
        source=SourceRef(type=c.source_type, id=c.source_id),
        age_days=c.age_days,
    )


def _bucket(candidates: list[_Candidate], name: str) -> list[FocusItem]:
    chosen = [c for c in candidates if c.bucket == name]
    chosen.sort(key=lambda c: (-c.age_days, c.source_type, c.source_id or 0))
    return [_item(c) for c in chosen]


def build_operator_view(db: Session, user: User) -> OperatorView:
    candidates = _candidates(db, user)
    ranked = _ranked(candidates)
    return OperatorView(
        approvals_waiting=_bucket(candidates, "approvals"),
        stale_projects=_bucket(candidates, "stale"),
        blocked_work=_bucket(candidates, "blocked"),
        tasks_safe_to_complete=_bucket(candidates, "safe_task"),
        recommended_next_actions=ranked[:RECOMMENDED_LIMIT],
        stale_threshold_days=STALE_DAYS,
        generated_at=utcnow(),
    )


def build_ranked_actions(db: Session, user: User) -> RankedActions:
    candidates = _candidates(db, user)
    return RankedActions(
        actions=_ranked(candidates),
        stale_threshold_days=STALE_DAYS,
        generated_at=utcnow(),
    )
