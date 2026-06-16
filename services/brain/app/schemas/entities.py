"""Read schemas for the core entities. All read from ORM attributes."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InboxItemRead(ORMModel):
    id: int
    user_id: int
    name: str
    body: str
    source: str
    status: str
    stage_history: list[Any]
    created_at: datetime


class ClassificationRecordRead(ORMModel):
    id: int
    item_id: int
    shape: str
    confidence: float
    recommended_route: str
    recommended_model_key: str
    resolved_model_id: str
    model_rationale: str
    reasoning_summary: str
    tags: list[Any]
    created_at: datetime


class PipelineRunRead(ORMModel):
    id: int
    item_id: int
    stage: str
    state: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ProjectRead(ORMModel):
    id: int
    item_id: int | None
    name: str
    slug: str
    stage: str
    mode: str
    plan_path: str | None
    plan_json: dict[str, Any]
    build_destination: str | None
    selected_integrations: list[Any]
    workspace: dict[str, Any]
    research_target_id: int | None
    created_at: datetime
    updated_at: datetime


class IntegrationRead(ORMModel):
    id: int
    user_id: int
    provider: str
    status: str
    credentials_ref: str | None
    created_at: datetime


class PMRunRead(ORMModel):
    id: int
    project_id: int
    status: str
    created_at: datetime


class ChecklistItem(BaseModel):
    id: str
    text: str
    done: bool = False


class TaskLabel(BaseModel):
    name: str
    # One of the brand palette colors, validated in the router: orange, green, gold, red, grey.
    color: str


class TaskRead(ORMModel):
    id: int
    user_id: int | None
    project_id: int | None
    title: str
    detail: str | None
    goal_for_agent: str | None
    timeline: str | None
    status: str
    priority: str
    due_date: date | None
    position: int
    checklist: list[ChecklistItem] = []
    labels: list[TaskLabel] = []
    source: str
    # The task's stored autonomy level (green, yellow, red). A response projection of the existing
    # column, so the web AutonomySelector reads the real per task level on reopen instead of falling
    # back to the project default. Defaults to yellow on a task that predates the dial.
    autonomy: str = "yellow"
    run_id: int | None
    # True when run_id points to a live agent run; the board surfaces these in Agent working.
    agent_active: bool = False
    created_at: datetime
    updated_at: datetime | None


class JournalNoteRead(ORMModel):
    id: int
    user_id: int | None
    body: str
    created_at: datetime


class AppSettingRead(ORMModel):
    id: int
    user_id: int | None
    key: str
    value: dict[str, Any]
    created_at: datetime
