"""Agent Build Engine schemas.

The request to start a build run for a task, and the run detail the review surface reads: the
proposed diff, the command transcript, the reasoning summary, the backend, and the cost. The diff
and transcript are projections of stored truth (the executor's diff step and the build step), never
a writable field. No provider key is ever present in any of these shapes.
"""

from datetime import datetime

from pydantic import BaseModel


class StartBuildRunRequest(BaseModel):
    """Start a build run for one task, optionally naming the backend (defaults to claude-code)."""

    task_id: int
    backend: str | None = None


class AgentRunDetail(BaseModel):
    """One build run with everything the review panel shows.

    status is the runtime roll up; phase is the build lifecycle marker (build, gate, merged,
    rolled_back, rejected, cancelled, failed). gate_step_id is the open human gate when the run is
    awaiting review, else null. diff and transcript are the full spilled text, capped server side.
    """

    id: int
    project_id: int | None
    task_id: int | None
    status: str
    kind: str
    phase: str | None
    backend: str | None
    reasoning_summary: str | None
    cost_usd: float | None
    goal_summary: str
    diff: str
    diff_shortstat: str
    diff_capped: bool
    transcript: str
    files_changed: list[str]
    gate_step_id: int | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
