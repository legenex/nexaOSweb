"""Runtime read schemas.

The runtime exposes reads only. There is no write schema here on purpose: the ledger is
authored solely through the four writers in app/runtime.py, never over HTTP. Every read is a
pure projection or aggregation of the stored truth.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator


class ResolveApprovalRequest(BaseModel):
    """The one human gate write: approve or reject a waiting_approval step, with an optional note.

    The runtime is read only otherwise; this resolves only the approval exit edge through the
    resolve_approval writer, never any other field.
    """

    resolution: Literal["approved", "rejected"]
    note: str = ""


class StepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    seq: int
    status: str
    kind: str
    title: str
    intent: str
    payload: dict[str, Any]
    proposed_by: str
    outcome: str | None
    evidence: list[Any]
    tool_call: dict[str, Any] | None
    failure: dict[str, Any] | None
    approval: dict[str, Any] | None
    correction_note: str | None
    corrected_from: str | None
    created_at: datetime
    updated_at: datetime


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    status: str
    kind: str
    autonomy_level: int
    branch_ref: str | None
    cursor_step_id: int | None
    plan: dict[str, Any]
    goal_summary: str
    context_summary: str
    schema_version: int
    proposed_by: str
    parent_run_id: int | None
    pm_run_id: int | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None

    @field_validator("kind", mode="before")
    @classmethod
    def _default_kind(cls, value: str | None) -> str:
        # A legacy row may carry a null kind. Never let it 500 the runtime list.
        return value or "general"


class ApprovalRequest(StepRead):
    """A waiting_approval step plus its gate guidance.

    Every approval request carries a recommended_default (proceed or change) and a one line
    framing, so a human sees a clear default and whether the decision materially affects the
    outcome.
    """

    recommended_default: str
    framing: str
    materially_affects: bool


class RunWithSteps(RunRead):
    steps: list[StepRead]


class ProofOfWork(BaseModel):
    """The evidence behind one step, and whether that evidence earned a verified status."""

    step_id: int
    status: str
    verified: bool
    evidence_count: int
    tool_evidence_count: int
    evidence: list[Any]
    tool_call: dict[str, Any] | None
