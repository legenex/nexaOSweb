"""Research request and read schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DepthLevel = Literal["quick", "standard", "deep"]
ScheduleMode = Literal["off", "daily", "weekly"]


class CreateProjectFromResearchRequest(BaseModel):
    # Optional overrides; name defaults to the research project's name, mode to the app default.
    name: str | None = Field(default=None, max_length=300)
    mode: str | None = None


class AttachRequest(BaseModel):
    target_project_id: int


class ResearchProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    topic: str = Field(default="", max_length=500)
    purpose: str = ""
    goals: list[str] = Field(default_factory=list)
    depth: DepthLevel = "standard"
    lookback: int = Field(default=30, ge=1, le=3650)
    schedule: ScheduleMode = "off"
    category: str = Field(default="general", max_length=80)


class ResearchProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    topic: str | None = Field(default=None, max_length=500)
    purpose: str | None = None
    goals: list[str] | None = None
    depth: DepthLevel | None = None
    lookback: int | None = Field(default=None, ge=1, le=3650)
    schedule: ScheduleMode | None = None
    category: str | None = Field(default=None, max_length=80)


class ResearchProjectRead(BaseModel):
    id: int
    name: str
    slug: str
    stage: str
    topic: str
    purpose: str
    goals: list[str]
    depth: str
    lookback: int
    schedule: str
    category: str
    research_target_id: int | None
    created_at: datetime
    updated_at: datetime


class GenerateConfigRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    name: str = ""


class GenerateConfigResponse(BaseModel):
    purpose: str
    goals: list[str]
    depth: DepthLevel
    lookback: int
    schedule: ScheduleMode


class ProjectUpdateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    kind: str
    title: str
    body: str
    source_ref: dict[str, Any]
    created_at: datetime


class ResearchFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    run_id: int | None
    title: str
    detail: str
    url: str | None
    status: str
    created_at: datetime


class ResearchRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    status: str
    summary: str
    analysis: str = ""
    key_takeaways: list[str] = []
    suggestions: list[str] = []
    findings_count: int
    created_at: datetime
    finished_at: datetime | None
    findings: list[ResearchFindingRead] = []
