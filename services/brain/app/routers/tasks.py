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
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.json_extract import synthesize_json
from app.models.base import utcnow
from app.models.runtime import AgentRun
from app.models.user import User
from app.models.workspace import Task
from app.routers.projects import _load_owned_project
from app.runtime import ACTIVE_RUN_STATUSES
from app.schemas.entities import TaskRead
from app.schemas.tasks import TaskCreate, TaskDraft, TaskDraftRequest, TaskUpdate
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
# Task priority. Defaults to med when the creator omits it.
PRIORITIES = ("low", "med", "high")
DEFAULT_PRIORITY = "med"


def _validate_status(value: str) -> None:
    if value not in STATUSES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"status must be one of {', '.join(STATUSES)}",
        )


def _validate_priority(value: str) -> None:
    if value not in PRIORITIES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"priority must be one of {', '.join(PRIORITIES)}",
        )


def _next_position(user: User, status_value: str, db: Session) -> int:
    """The next ordering slot at the end of a status column for this user's tasks."""
    highest = (
        db.query(func.max(Task.position))
        .filter(
            Task.deleted_at.is_(None),
            (Task.user_id == user.id) | (Task.user_id.is_(None)),
            Task.status == status_value,
        )
        .scalar()
    )
    return (highest or 0) + 1


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
    priority = payload.priority or DEFAULT_PRIORITY
    _validate_priority(priority)
    if payload.project_id is not None:
        # The link is enforced here, not by a FK: the project must exist and be the user's.
        _load_owned_project(payload.project_id, user, db)
    task = Task(
        user_id=user.id,
        project_id=payload.project_id,
        title=payload.title.strip(),
        detail=payload.detail,
        goal_for_agent=payload.goal_for_agent,
        timeline=payload.timeline,
        status=initial_status,
        priority=priority,
        due_date=payload.due_date,
        position=_next_position(user, initial_status, db),
        source="manual",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.post("/generate", response_model=TaskDraft)
def generate_task_draft(
    payload: TaskDraftRequest,
    _user: User = Depends(current_user),
) -> TaskDraft:
    """Expand a rough title or description into a structured draft for the New Task dialog.

    This returns a draft only, it never creates the task, so the human stays in the gate: the
    dialog fills its fields from the draft and the user reviews before adding. The model is chosen
    by the general semantic key through the router, never a hardcoded model id.
    """
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "notes": {"type": "string"},
            "goal_for_agent": {"type": "string"},
            "priority": {"type": "string", "enum": list(PRIORITIES)},
            "timeline": {"type": "string"},
        },
        "required": ["title", "notes", "goal_for_agent", "priority", "timeline"],
    }
    prompt = (
        "Expand this rough task into a structured draft for a personal operating system. "
        f"Rough input: {payload.prompt}\n\n"
        "Return a concise title, notes (one to three sentences describing the task), "
        "goal_for_agent (what an agent should achieve to complete it), a priority of low, med, "
        "or high, and a loose timeline such as today, this week, or this month."
    )
    draft = synthesize_json("general", prompt, schema)

    priority = str(draft.get("priority", "") or "").lower()
    if priority not in PRIORITIES:
        priority = DEFAULT_PRIORITY
    return TaskDraft(
        title=str(draft.get("title") or payload.prompt).strip()[:300],
        notes=str(draft.get("notes") or ""),
        goal_for_agent=str(draft.get("goal_for_agent") or ""),
        priority=priority,
        timeline=str(draft.get("timeline") or ""),
    )


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
    # Order within a status by position, then newest first as a stable tie break for the board.
    tasks = query.order_by(
        Task.position.asc(), Task.created_at.desc(), Task.id.desc()
    ).all()

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
    if "priority" in changes and changes["priority"] is not None:
        _validate_priority(changes["priority"])
    if "project_id" in changes and changes["project_id"] is not None:
        _load_owned_project(changes["project_id"], user, db)
    if "title" in changes and changes["title"] is not None:
        changes["title"] = changes["title"].strip()
    for field, value in changes.items():
        # status, priority, and position are not null columns: a null is a no op. Every other
        # provided field is applied (a null clears it).
        if field in ("status", "priority", "position") and value is None:
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
