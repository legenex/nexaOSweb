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


class ReadinessItem(BaseModel):
    """One readiness item: a need the plan declared and how the assessment resolved it.

    provider and integration_id are present only for a credential item, so the web can open the
    provide control. Neither is or carries a secret value.
    """

    step_id: int
    key: str | None = None
    question: str | None = None
    item_kind: str | None = None
    category: str
    blocking: bool = False
    resolution: str | None = None
    source: str | None = None
    status: str
    satisfied: bool = False
    provider: str | None = None
    integration_id: int | None = None


class ReadinessAssessment(BaseModel):
    """A project's build readiness: every item, whether it is satisfied, and what still blocks."""

    run_id: int
    project_id: int | None = None
    kind: str
    satisfied: bool
    items: list[ReadinessItem] = []
    blocking_open: list[str] = []


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
