"""Router across the eight workflows.

Reads the item's decision record and dispatches by recommended route:

- project: create a Project at stage idea, continues into Process.
- tasks: attach a Task to a get or create Inbox Tasks project.
- journal: create a JournalNote.
- technical, campaign, content, park, archive: resolve to their workflow state with no
  deep processing.

Items below the confidence threshold are escalated and stay in the inbox. Every routing
is recorded on a PipelineRun and on the item stage_history.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.classify import get_confidence_threshold
from app.models.base import utcnow
from app.models.inbox import ClassificationRecord, InboxItem, PipelineRun
from app.models.project import Project
from app.models.workspace import JournalNote, Task
from app.project_modes import destination_for, is_valid_mode
from app.util import slugify

logger = logging.getLogger(__name__)

TERMINAL_ROUTES = {"technical", "campaign", "content", "park", "archive"}


@dataclass
class RouteResult:
    route: str
    state: str
    created_kind: str | None = None
    created_id: int | None = None
    project_id: int | None = None


def _latest_record(db: Session, item_id: int) -> ClassificationRecord | None:
    return (
        db.query(ClassificationRecord)
        .filter(ClassificationRecord.item_id == item_id)
        .order_by(ClassificationRecord.created_at.desc(), ClassificationRecord.id.desc())
        .first()
    )


def _captured_mode(item: InboxItem) -> str | None:
    """The project mode chosen at capture, read back from the item's stage history."""
    for entry in item.stage_history or []:
        if isinstance(entry, dict) and entry.get("stage") == "capture":
            mode = entry.get("mode")
            if is_valid_mode(mode):
                return str(mode)
    return None


def get_or_create_project_for_item(db: Session, item: InboxItem) -> Project:
    """Return the item's project, creating it if absent. Safe under the race between the
    background router and the Process stage: the unique index on item_id means one creator
    wins and the other refetches the winner."""
    existing = db.query(Project).filter(Project.item_id == item.id).first()
    if existing is not None:
        return existing
    mode = _captured_mode(item)
    try:
        with db.begin_nested():
            project = Project(
                item_id=item.id, name=item.name, slug=slugify(item.name), stage="idea"
            )
            # A mode chosen at capture sets the project mode and its default destination.
            if mode is not None:
                project.mode = mode
                project.build_destination = destination_for(mode)
            db.add(project)
            db.flush()
        return project
    except IntegrityError:
        return db.query(Project).filter(Project.item_id == item.id).first()


def get_or_create_inbox_tasks_project(db: Session) -> Project:
    project = db.query(Project).filter(Project.slug == "inbox-tasks").first()
    if project is None:
        project = Project(item_id=None, name="Inbox Tasks", slug="inbox-tasks", stage="idea")
        db.add(project)
        db.flush()
    return project


def route_item(db: Session, item: InboxItem) -> RouteResult:
    record = _latest_record(db, item.id)
    run = PipelineRun(item_id=item.id, stage="route", state="pending", started_at=utcnow())
    db.add(run)

    if record is None:
        run.state = "skipped"
        run.finished_at = utcnow()
        db.commit()
        return RouteResult(route="none", state="skipped")

    if record.confidence < get_confidence_threshold(db):
        item.status = "escalated"
        item.stage_history = [*item.stage_history, {"stage": "route", "state": "escalated"}]
        run.state = "escalated"
        run.finished_at = utcnow()
        db.commit()
        return RouteResult(route=record.recommended_route, state="escalated")

    route = record.recommended_route
    created_kind: str | None = None
    created_id: int | None = None
    project_id: int | None = None

    if route == "project":
        project = get_or_create_project_for_item(db, item)
        created_kind, created_id, project_id = "project", project.id, project.id

    elif route == "tasks":
        project = get_or_create_inbox_tasks_project(db)
        task = Task(user_id=item.user_id, project_id=project.id, title=item.name, status="todo")
        db.add(task)
        db.flush()
        created_kind, created_id, project_id = "task", task.id, project.id

    elif route == "journal":
        note = JournalNote(user_id=item.user_id, body=item.body or item.name)
        db.add(note)
        db.flush()
        created_kind, created_id = "journal_note", note.id

    # Terminal routes create no artifact and simply resolve.
    item.status = "routed"
    item.stage_history = [
        *item.stage_history,
        {"stage": "route", "route": route, "state": "done"},
    ]
    run.state = "done"
    run.finished_at = utcnow()
    db.commit()
    return RouteResult(
        route=route,
        state="done",
        created_kind=created_kind,
        created_id=created_id,
        project_id=project_id,
    )
