"""Router across the eight workflows."""

from app.agents.route import route_item
from app.models.inbox import ClassificationRecord, InboxItem
from app.models.project import Project
from app.models.user import User
from app.models.workspace import JournalNote, Task


def _item_with_record(db_session, route, model_key="agentic_code", shape="project", confidence=0.9):
    user = db_session.query(User).first()
    if user is None:
        user = User(email="r@example.com", password_hash="x")
        db_session.add(user)
        db_session.flush()
    item = InboxItem(
        user_id=user.id, name="A thing", body="details", status="classified", stage_history=[]
    )
    db_session.add(item)
    db_session.flush()
    db_session.add(
        ClassificationRecord(
            item_id=item.id,
            shape=shape,
            confidence=confidence,
            recommended_route=route,
            recommended_model_key=model_key,
            resolved_model_id="x",
            model_rationale="r",
            reasoning_summary="s",
            tags=[],
        )
    )
    db_session.commit()
    return item


def test_project_route_creates_project(db_session):
    item = _item_with_record(db_session, "project")
    result = route_item(db_session, item)
    assert result.created_kind == "project"
    project = db_session.query(Project).filter(Project.item_id == item.id).first()
    assert project is not None
    assert project.stage == "idea"
    assert item.status == "routed"


def test_tasks_route_attaches_to_inbox_tasks(db_session):
    item = _item_with_record(db_session, "tasks", model_key="bulk", shape="gtd")
    result = route_item(db_session, item)
    assert result.created_kind == "task"
    inbox = db_session.query(Project).filter(Project.slug == "inbox-tasks").first()
    assert inbox is not None
    task = db_session.query(Task).first()
    assert task.project_id == inbox.id
    # A second task reuses the same Inbox Tasks project.
    item2 = _item_with_record(db_session, "tasks", model_key="bulk", shape="gtd")
    route_item(db_session, item2)
    assert db_session.query(Project).filter(Project.slug == "inbox-tasks").count() == 1


def test_journal_route_creates_note(db_session):
    item = _item_with_record(db_session, "journal", model_key="journal_reflection", shape="private")
    result = route_item(db_session, item)
    assert result.created_kind == "journal_note"
    assert db_session.query(JournalNote).count() == 1


def test_terminal_route_creates_no_artifact(db_session):
    item = _item_with_record(db_session, "archive", model_key="bulk", shape="archive")
    result = route_item(db_session, item)
    assert result.created_kind is None
    assert item.status == "routed"
    assert db_session.query(Project).count() == 0


def test_low_confidence_escalates_and_stays(db_session):
    item = _item_with_record(db_session, "project", confidence=0.2)
    result = route_item(db_session, item)
    assert result.state == "escalated"
    assert item.status == "escalated"
    assert db_session.query(Project).count() == 0
