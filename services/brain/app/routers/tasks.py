"""Task endpoints.

Tasks carry a title, an optional longer detail, a status, an optional build project link, a
source (manual, research, or run), and an optional run_id seam to the agent run that produced
them. Reminders fold in here: there is no separate Reminders surface. Tasks are soft deleted (a
deleted task keeps its row and stays recoverable) and are excluded from default lists and from the
open task counts surfaced on the Dashboard and Insights.

Research already creates tasks from findings (see the research router), and Insights creates them
from signals; this module owns the standalone task surface and its CRUD.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.base import utcnow
from app.models.runtime import AgentRun
from app.models.user import User
from app.models.workspace import Task
from app.routers.projects import _load_owned_project
from app.runtime import ACTIVE_RUN_STATUSES
from app.schemas.entities import TaskRead
from app.schemas.tasks import TaskCreate, TaskUpdate
from app.security.auth import current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])

# The Hermes board columns, in order. New tasks default to todo and move between these.
BOARD_STATUSES = ("todo", "doing", "agent_working", "review", "done")
# The full accepted set. archived is the soft hidden state (not a board column). blocked is a
# secondary state that Focus still recognizes as a blocker; the board folds it into Doing. New
# tasks never enter blocked, it survives only for legacy rows and the Focus blocker bucket.
STATUSES = (*BOARD_STATUSES, "archived", "blocked")
DEFAULT_STATUS = "todo"
# How a task came to exist. Set by the creator, not editable after the fact.
SOURCES = ("manual", "research", "run")


def _validate_status(value: str) -> None:
    if value not in STATUSES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"status must be one of {', '.join(STATUSES)}",
        )


def _load_task(task_id: int, user: User, db: Session) -> Task:
    task = db.get(Task, task_id)
    visible = task is not None and task.deleted_at is None
    owned = task is not None and task.user_id in (None, user.id)
    if not (visible and owned):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
    return task


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Task:
    initial_status = payload.status or DEFAULT_STATUS
    _validate_status(initial_status)
    if payload.project_id is not None:
        # The link is enforced here, not by a FK: the project must exist and be the user's.
        _load_owned_project(payload.project_id, user, db)
    task = Task(
        user_id=user.id,
        project_id=payload.project_id,
        title=payload.title.strip(),
        detail=payload.detail,
        status=initial_status,
        source="manual",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("", response_model=list[TaskRead])
def list_tasks(
    project_id: int | None = Query(None, description="filter to tasks under this project"),
    status_filter: str | None = Query(
        None, alias="status", description="filter to a single status"
    ),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[TaskRead]:
    query = db.query(Task).filter(
        Task.deleted_at.is_(None),
        (Task.user_id == user.id) | (Task.user_id.is_(None)),
    )
    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    if status_filter is not None:
        _validate_status(status_filter)
        query = query.filter(Task.status == status_filter)
    tasks = query.order_by(Task.created_at.desc(), Task.id.desc()).all()

    # A task whose run_id points to a live AgentRun is surfaced in the Agent working column.
    active_run_ids = {
        row[0]
        for row in db.query(AgentRun.id).filter(AgentRun.status.in_(ACTIVE_RUN_STATUSES)).all()
    }
    reads: list[TaskRead] = []
    for task in tasks:
        read = TaskRead.model_validate(task)
        read.agent_active = task.run_id is not None and task.run_id in active_run_ids
        reads.append(read)
    return reads


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Task:
    return _load_task(task_id, user, db)


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Task:
    task = _load_task(task_id, user, db)
    # exclude_unset keeps the omit versus explicit null distinction: an omitted project_id leaves
    # the link unchanged, an explicit null detaches the task from its project.
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] is not None:
        _validate_status(changes["status"])
    if "project_id" in changes and changes["project_id"] is not None:
        _load_owned_project(changes["project_id"], user, db)
    if "title" in changes and changes["title"] is not None:
        changes["title"] = changes["title"].strip()
    for field, value in changes.items():
        # A null status is a no op; every other provided field is applied (null clears it).
        if field == "status" and value is None:
            continue
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    # Soft delete: flag the row, keep it recoverable, and drop it from default lists and counts.
    task = _load_task(task_id, user, db)
    task.deleted_at = utcnow()
    db.commit()
