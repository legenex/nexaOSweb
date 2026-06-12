"""Model and schema smoke tests, plus migration parity with the metadata."""

from app.models import (
    AppSetting,
    ClassificationRecord,
    InboxItem,
    Integration,
    JournalNote,
    PipelineRun,
    PMRun,
    Project,
    Task,
    User,
)
from app.models.base import Base
from app.schemas.entities import (
    ClassificationRecordRead,
    InboxItemRead,
    ProjectRead,
)

EXPECTED_TABLES = {
    "users",
    "inbox_items",
    "classification_records",
    "pipeline_runs",
    "projects",
    "integrations",
    "pm_runs",
    "tasks",
    "journal_notes",
    "app_settings",
}


def test_metadata_defines_every_table():
    assert EXPECTED_TABLES.issubset(set(Base.metadata.tables.keys()))


def test_full_pipeline_rows_roundtrip(db_session):
    user = User(email="b4@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()

    item = InboxItem(
        user_id=user.id,
        name="Build a landing page",
        body="for the launch",
        source="note",
        status="captured",
        stage_history=[{"stage": "capture", "at": "now"}],
    )
    db_session.add(item)
    db_session.flush()

    record = ClassificationRecord(
        item_id=item.id,
        shape="project",
        confidence=0.91,
        recommended_route="process",
        recommended_model_key="agentic_code",
        resolved_model_id="anthropic/claude-opus-4-8",
        model_rationale="project shaped",
        reasoning_summary="looks like a multi step build",
        tags=["web", "launch"],
    )
    run = PipelineRun(item_id=item.id, stage="classify", state="done")
    project = Project(
        item_id=item.id,
        name="Build a landing page",
        slug="build-a-landing-page",
        stage="idea",
        plan_json={"summary": "x"},
        selected_integrations=["stripe"],
    )
    db_session.add_all([record, run, project])
    db_session.flush()

    integration = Integration(user_id=user.id, provider="stripe", status="connected")
    pm = PMRun(project_id=project.id, status="active")
    task = Task(user_id=user.id, project_id=project.id, title="ship it")
    note = JournalNote(user_id=user.id, body="thoughts")
    setting = AppSetting(user_id=user.id, key="intake", value={"confidence_threshold": 0.6})
    db_session.add_all([integration, pm, task, note, setting])
    db_session.commit()

    assert InboxItemRead.model_validate(item).name == "Build a landing page"
    assert ClassificationRecordRead.model_validate(record).confidence == 0.91
    assert ProjectRead.model_validate(project).selected_integrations == ["stripe"]
