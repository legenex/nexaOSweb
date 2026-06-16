"""Agent Build Engine endpoints: start a gated build run for a task, review it, resolve it.

A build run drives an external coding agent (claude-code) through the executor's proven gated spine.
These endpoints own the write surface the runtime router deliberately does not: start a run, read
its diff and transcript, and approve, reject, or cancel it. The provider key is read from server
settings only and never enters a prompt or a response. Ownership is gated through the run's project,
the same rule the runtime reads use.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.agents.build_engine import (
    BackendUnavailableError,
    BuildEngineError,
    KillSwitchEngagedError,
    approve_build_run,
    build_run_detail,
    cancel_build_run,
    engage_kill_switch,
    is_build_run,
    reject_build_run,
    release_kill_switch,
    set_project_autonomy_default,
    set_task_autonomy,
    start_build_run,
)
from app.agents.orchestrator import (
    OrchestratorDisabledError,
    OrchestratorHaltedError,
    OrchestratorNotApprovedError,
    OrchestratorPausedError,
    orchestrate_project,
    orchestration_state,
    pause_loop,
    resume_loop,
)
from app.agents.slicer import SlicerError, slice_plan, task_graph
from app.audit import CATEGORY_ACTIONS
from app.db import get_db
from app.models.audit import AgentAudit
from app.models.inbox import InboxItem
from app.models.project import Project
from app.models.runtime import AgentRun
from app.models.user import User
from app.models.workspace import Task
from app.schemas.agents import (
    AgentRunDetail,
    KillSwitchRequest,
    OrchestrateRequest,
    OrchestrationState,
    ProjectAutonomyState,
    SetProjectAutonomyRequest,
    SetTaskAutonomyRequest,
    StartBuildRunRequest,
    TaskAutonomyState,
    TaskGraph,
)
from app.schemas.audit import AuditRead
from app.security.auth import current_user

router = APIRouter(prefix="/agents", tags=["agents"])


def _user_owns_project(project_id: int | None, user: User, db: Session) -> bool:
    # A run with no project is a system run, visible to the authenticated user. A project linked to
    # an inbox item is owned by that item's user; an unlinked project is shared.
    if project_id is None:
        return True
    project = db.get(Project, project_id)
    if project is None:
        return False
    if project.item_id is None:
        return True
    item = db.get(InboxItem, project.item_id)
    return item is not None and item.user_id == user.id


def _load_task(task_id: int, user: User, db: Session) -> Task:
    task = db.get(Task, task_id)
    visible = task is not None and task.deleted_at is None
    owned = task is not None and task.user_id in (None, user.id)
    if not (visible and owned):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
    return task


def _load_build_run(run_id: int, user: User, db: Session) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None or not is_build_run(run) or not _user_owns_project(run.project_id, user, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return run


def _load_project(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None or not _user_owns_project(project_id, user, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return project


def _project_autonomy_state(project: Project, halted_run_ids: list[int] | None = None):
    return ProjectAutonomyState(
        project_id=project.id,
        default_level=project.agent_autonomy_default,
        kill_switch_engaged=project.agent_kill_switch,
        halted_run_ids=halted_run_ids or [],
    )


@router.post("/runs", response_model=AgentRunDetail, status_code=status.HTTP_201_CREATED)
def start_run(
    payload: StartBuildRunRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AgentRunDetail:
    """Start a gated build run for one task, returned parked at the human gate (awaiting review).

    The task must be the user's and belong to a project. The backend must be available in this
    environment (the CLI installed and the key set, server side); when it is not, this returns 503
    so the dev environment is told plainly rather than starting a run that cannot work.
    """
    task = _load_task(payload.task_id, user, db)
    try:
        run = start_build_run(
            db, task=task, backend_name=payload.backend, proposed_by=user.email or "user"
        )
    except KillSwitchEngagedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except BackendUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except BuildEngineError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return AgentRunDetail(**build_run_detail(db, run))


@router.get("/runs/{run_id}", response_model=AgentRunDetail)
def get_run(
    run_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AgentRunDetail:
    """Return a build run with its diff, transcript, reasoning summary, backend, and cost."""
    run = _load_build_run(run_id, user, db)
    return AgentRunDetail(**build_run_detail(db, run))


@router.post("/runs/{run_id}/approve", response_model=AgentRunDetail)
def approve_run(
    run_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AgentRunDetail:
    """Approve the run: promote the diff into the project repo through the executor merge path."""
    run = _load_build_run(run_id, user, db)
    try:
        run = approve_build_run(db, run, resolved_by=user.email or "user")
    except BuildEngineError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return AgentRunDetail(**build_run_detail(db, run))


@router.post("/runs/{run_id}/reject", response_model=AgentRunDetail)
def reject_run(
    run_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AgentRunDetail:
    """Reject the run: discard the diff through the rollback path and restore the task status."""
    run = _load_build_run(run_id, user, db)
    try:
        run = reject_build_run(db, run, resolved_by=user.email or "user")
    except BuildEngineError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return AgentRunDetail(**build_run_detail(db, run))


@router.post("/runs/{run_id}/cancel", response_model=AgentRunDetail)
def cancel_run(
    run_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AgentRunDetail:
    """Cancel an active run and return the task to its prior status."""
    run = _load_build_run(run_id, user, db)
    try:
        run = cancel_build_run(db, run, resolved_by=user.email or "user")
    except BuildEngineError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return AgentRunDetail(**build_run_detail(db, run))


# --- the autonomy dial and the kill switch ------------------------------------------------


@router.put("/tasks/{task_id}/autonomy", response_model=TaskAutonomyState)
def set_task_autonomy_level(
    task_id: int,
    payload: SetTaskAutonomyRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TaskAutonomyState:
    """Set a task's autonomy level: green runs unattended, yellow gates, red never auto runs."""
    task = _load_task(task_id, user, db)
    try:
        task = set_task_autonomy(db, task, payload.level)
    except BuildEngineError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return TaskAutonomyState(task_id=task.id, level=task.autonomy)


@router.get("/projects/{project_id}/autonomy", response_model=ProjectAutonomyState)
def get_project_autonomy(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProjectAutonomyState:
    """Read a project's autonomy default and kill switch state, for the prominent UI control."""
    project = _load_project(project_id, user, db)
    return _project_autonomy_state(project)


@router.put("/projects/{project_id}/autonomy", response_model=ProjectAutonomyState)
def set_project_autonomy(
    project_id: int,
    payload: SetProjectAutonomyRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProjectAutonomyState:
    """Set a project's default autonomy level that new tasks inherit."""
    project = _load_project(project_id, user, db)
    try:
        project = set_project_autonomy_default(db, project, payload.default_level)
    except BuildEngineError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _project_autonomy_state(project)


@router.post("/projects/{project_id}/kill-switch", response_model=ProjectAutonomyState)
def set_project_kill_switch(
    project_id: int,
    payload: KillSwitchRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProjectAutonomyState:
    """Engage or release the project kill switch. Engaging halts every in flight run for the project
    and refuses new ones until released; the halted run ids are returned."""
    project = _load_project(project_id, user, db)
    halted_ids: list[int] = []
    if payload.engaged:
        halted = engage_kill_switch(db, project, resolved_by=user.email or "user")
        halted_ids = [run.id for run in halted]
    else:
        release_kill_switch(db, project)
    db.refresh(project)
    return _project_autonomy_state(project, halted_ids)


# --- plan to tasks slicer -----------------------------------------------------------------


@router.post("/projects/{project_id}/slice", response_model=TaskGraph)
def slice_project_plan(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TaskGraph:
    """Slice the project's current plan into ordered buildable tasks and return the task graph.

    Idempotent: re-slicing the same plan reconciles in place rather than duplicating. A plan with no
    buildable units, or a malformed plan_json, is rejected with 400.
    """
    project = _load_project(project_id, user, db)
    try:
        graph = slice_plan(db, project, proposed_by=user.email or "user")
    except SlicerError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return TaskGraph(**graph)


@router.get("/projects/{project_id}/tasks", response_model=TaskGraph)
def get_project_task_graph(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TaskGraph:
    """Return the project's build task graph: the generated tasks, ordered, with their dependencies
    and current status."""
    project = _load_project(project_id, user, db)
    return TaskGraph(**task_graph(db, project))


# --- the orchestrator loop ----------------------------------------------------------------


@router.post("/projects/{project_id}/orchestrate", response_model=OrchestrationState)
def orchestrate_project_loop(
    project_id: int,
    payload: OrchestrateRequest | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> OrchestrationState:
    """Run the orchestration loop for a project and return its state.

    Refused when the orchestrator flag is off (403), when the kill switch is engaged, when the
    project is not approved, or when the loop is paused (409). Green tasks auto advance and unlock
    dependents; yellow and red tasks park at the gate. The loop is bounded by a run cap and a
    wall-clock budget.
    """
    project = _load_project(project_id, user, db)
    payload = payload or OrchestrateRequest()
    try:
        state = orchestrate_project(
            db,
            project,
            run_cap=payload.run_cap,
            budget_seconds=payload.budget_seconds,
            proposed_by=user.email or "user",
        )
    except OrchestratorDisabledError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except (
        OrchestratorNotApprovedError,
        OrchestratorHaltedError,
        OrchestratorPausedError,
    ) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return OrchestrationState(**state)


# --- the governance audit log (read only) -------------------------------------------------

# A read cap so a single call can never stream the whole log. The reads are newest first, so the
# default window is the most recent activity; a caller paginates with a tighter filter.
_AUDIT_DEFAULT_LIMIT = 200
_AUDIT_MAX_LIMIT = 1000


def _visible_audit(rows: list[AgentAudit], user: User, db: Session) -> list[AgentAudit]:
    return [row for row in rows if _user_owns_project(row.project_id, user, db)]


@router.get("/audit", response_model=list[AuditRead])
def list_audit(
    project_id: int | None = Query(None),
    run_id: int | None = Query(None),
    category: str | None = Query(None),
    actor: str | None = Query(None),
    limit: int = Query(_AUDIT_DEFAULT_LIMIT, ge=1, le=_AUDIT_MAX_LIMIT),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[AgentAudit]:
    """The cross run governance feed, newest first, filterable by project, run, category, actor."""
    if category is not None and category not in CATEGORY_ACTIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown category {category!r}")
    if project_id is not None and not _user_owns_project(project_id, user, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")

    query = db.query(AgentAudit)
    if project_id is not None:
        query = query.filter(AgentAudit.project_id == project_id)
    if run_id is not None:
        query = query.filter(AgentAudit.run_id == run_id)
    if category is not None:
        query = query.filter(AgentAudit.category == category)
    if actor is not None:
        query = query.filter(AgentAudit.actor == actor)
    rows = query.order_by(AgentAudit.created_at.desc(), AgentAudit.id.desc()).all()
    return _visible_audit(rows, user, db)[:limit]


@router.get("/projects/{project_id}/audit", response_model=list[AuditRead])
def list_project_audit(
    project_id: int,
    category: str | None = Query(None),
    actor: str | None = Query(None),
    limit: int = Query(_AUDIT_DEFAULT_LIMIT, ge=1, le=_AUDIT_MAX_LIMIT),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[AgentAudit]:
    """Every governance event recorded for one project, newest first."""
    _load_project(project_id, user, db)
    if category is not None and category not in CATEGORY_ACTIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown category {category!r}")

    query = db.query(AgentAudit).filter(AgentAudit.project_id == project_id)
    if category is not None:
        query = query.filter(AgentAudit.category == category)
    if actor is not None:
        query = query.filter(AgentAudit.actor == actor)
    rows = query.order_by(AgentAudit.created_at.desc(), AgentAudit.id.desc()).all()
    return rows[:limit]


@router.get("/projects/{project_id}/orchestration", response_model=OrchestrationState)
def get_orchestration_state(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> OrchestrationState:
    """Return the orchestration loop state and per task progress for a project."""
    project = _load_project(project_id, user, db)
    return OrchestrationState(**orchestration_state(db, project))


@router.post("/projects/{project_id}/pause", response_model=OrchestrationState)
def pause_orchestration(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> OrchestrationState:
    """Pause the orchestration loop: new dispatch is refused until it is resumed."""
    project = _load_project(project_id, user, db)
    return OrchestrationState(**pause_loop(db, project))


@router.post("/projects/{project_id}/resume", response_model=OrchestrationState)
def resume_orchestration(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> OrchestrationState:
    """Resume a paused orchestration loop so the next orchestrate call may run."""
    project = _load_project(project_id, user, db)
    return OrchestrationState(**resume_loop(db, project))
