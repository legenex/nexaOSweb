"""Dashboard Command Radar and brief schemas.

The summary is the aggregate state behind the Command Radar: counts and short lists. The
brief is a time aware narrative, cached per day and per mode.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

BriefMode = Literal["morning", "evening"]


class ProjectBrief(BaseModel):
    id: int
    name: str
    stage: str
    build_destination: str | None = None


class ItemBrief(BaseModel):
    id: int
    name: str
    source: str
    created_at: datetime


class TaskBrief(BaseModel):
    id: int
    title: str
    status: str
    project_id: int | None = None


class ResearchFinding(BaseModel):
    id: int
    name: str
    shape: str
    confidence: float


class Opportunity(BaseModel):
    title: str
    detail: str
    score: float | None = None


class ConnectorHealth(BaseModel):
    provider: str
    status: str


class ModelUsage(BaseModel):
    model_key: str
    model_id: str
    count: int


class BrainStatus(BaseModel):
    status: str
    version: str
    database_connected: bool
    dreaming_enabled: bool
    sweep_enabled: bool
    last_dream_at: datetime | None = None


class DashboardSummary(BaseModel):
    active_projects: list[ProjectBrief]
    active_projects_count: int
    builds_awaiting_approval: list[ProjectBrief]
    builds_awaiting_approval_count: int
    research_ready: list[ResearchFinding]
    research_ready_count: int
    suggested_tasks: list[TaskBrief]
    suggested_tasks_count: int
    top_opportunity: Opportunity | None = None
    recent_uploads: list[ItemBrief]
    connector_health: list[ConnectorHealth]
    model_usage: list[ModelUsage]
    brain: BrainStatus


class DashboardBrief(BaseModel):
    mode: BriefMode
    date: str
    generated_at: datetime
    cached: bool
    text: str
