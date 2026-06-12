"""Flow stage request and response schemas."""

from typing import Any

from pydantic import BaseModel


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
