"""Agent Build Engine endpoints: start a gated build run for a task, review it, resolve it.

A build run drives an external coding agent (claude-code) through the executor's proven gated spine.
These endpoints own the write surface the runtime router deliberately does not: start a run, read
its diff and transcript, and approve, reject, or cancel it. The provider key is read from server
settings only and never enters a prompt or a response. Ownership is gated through the run's project,
the same rule the runtime reads use.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.build_engine import (
    BackendUnavailableError,
    BuildEngineError,
    approve_build_run,
    build_run_detail,
    cancel_build_run,
    is_build_run,
    reject_build_run,
    start_build_run,
)
from app.db import get_db
from app.models.inbox import InboxItem
from app.models.project import Project
from app.models.runtime import AgentRun
from app.models.user import User
from app.models.workspace import Task
from app.schemas.agents import AgentRunDetail, StartBuildRunRequest
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
