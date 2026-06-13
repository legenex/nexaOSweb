"""Research request and read schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AttachRequest(BaseModel):
    target_project_id: int


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
    findings_count: int
    created_at: datetime
    finished_at: datetime | None
    findings: list[ResearchFindingRead] = []
