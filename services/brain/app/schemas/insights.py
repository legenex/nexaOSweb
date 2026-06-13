"""Insights request and read schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

InsightCategory = Literal["personal_pattern", "work_pattern", "profile_summary", "innovation"]
IdeaKind = Literal["project", "revenue", "automation"]
InsightStatus = Literal[
    "active", "saved", "tasked", "project_created", "dismissed", "superseded"
]


class InsightRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    category: str
    idea_kind: str | None
    title: str
    body: str
    confidence: float
    source: str
    reasoning: str
    source_refs: list[Any]
    status: str
    action_ref: dict[str, Any]
    created_at: datetime


class InsightsResponse(BaseModel):
    """The cached latest batch, grouped by category for the four surfaces."""

    run_id: int | None
    generated_at: datetime | None
    extraction_model_key: str | None
    synthesis_model_key: str | None
    personal_patterns: list[InsightRead] = []
    work_patterns: list[InsightRead] = []
    profile_summary: InsightRead | None = None
    innovation: list[InsightRead] = []


class SaveToKnowledgeResponse(BaseModel):
    insight_id: int
    knowledge_entry_id: int
    status: str


class CreateTaskResponse(BaseModel):
    insight_id: int
    task_id: int
    status: str


class CreateProjectResponse(BaseModel):
    insight_id: int
    project_id: int
    status: str
