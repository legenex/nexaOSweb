"""Focus schemas: the operator view and the explainable ranked next-actions list.

Both are read only. A SourceRef points every item back to where it came from (a project, an agent
run, a task, or the Dreaming queue) so the surface can link to its source. The ranked list adds a
score, a one line reason, and the four factors the score is built from.
"""

from datetime import datetime

from pydantic import BaseModel


class SourceRef(BaseModel):
    # One of project, run, task, dreaming. id is null only for the Dreaming review queue, which is
    # a place rather than a single row.
    type: str
    id: int | None = None


class FocusItem(BaseModel):
    kind: str
    title: str
    detail: str
    source: SourceRef
    age_days: int


class FocusFactors(BaseModel):
    age_days: int
    # low, medium, or high.
    risk: str
    blocked: bool
    # True when the action is fully safe-set: an agent could take it if autonomy were raised.
    autonomy_eligible: bool


class RankedAction(BaseModel):
    rank: int
    kind: str
    title: str
    detail: str
    source: SourceRef
    score: float
    # The plain language explanation of why the action sits at this rank.
    reason: str
    factors: FocusFactors


class OperatorView(BaseModel):
    approvals_waiting: list[FocusItem]
    stale_projects: list[FocusItem]
    blocked_work: list[FocusItem]
    tasks_safe_to_complete: list[FocusItem]
    recommended_next_actions: list[RankedAction]
    stale_threshold_days: int
    generated_at: datetime


class RankedActions(BaseModel):
    actions: list[RankedAction]
    stale_threshold_days: int
    generated_at: datetime
