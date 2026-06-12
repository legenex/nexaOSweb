"""Flow stage request and response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.entities import ClassificationRecordRead


class SuggestedIntegration(BaseModel):
    provider: str
    status: str  # "connected" or "available"
    integration_id: int | None = None


class ClarifyResponse(BaseModel):
    clarifying_questions: list[str]
    suggested_integrations: list[SuggestedIntegration]


class ClarifyRequest(BaseModel):
    answers: dict[str, str] = {}
    selected_integration_ids: list[int] = []
    scope_changes: dict[str, Any] = {}


class PromoteResponse(BaseModel):
    project_id: int
    stage: str
    pm_run_id: int
    requirements_path: str


class FlowItemDTO(BaseModel):
    id: int
    name: str
    source: str
    status: str
    created_at: datetime
    classification: ClassificationRecordRead | None = None
    route: str | None = None
    project_id: int | None = None
    project_stage: str | None = None
    plan_available: bool = False
    preview_available: bool = False
    build_destination: str | None = None
    selected_integrations: list[Any] = []
    gate_state: str = "none"
