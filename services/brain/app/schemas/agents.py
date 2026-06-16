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


class SetTaskAutonomyRequest(BaseModel):
    """Set a task's autonomy level: green, yellow, or red."""

    level: str


class TaskAutonomyState(BaseModel):
    """A task's current autonomy level."""

    task_id: int
    level: str


class SetProjectAutonomyRequest(BaseModel):
    """Set a project's default autonomy level that new tasks inherit: green, yellow, or red."""

    default_level: str


class KillSwitchRequest(BaseModel):
    """Engage or release a project's agent kill switch."""

    engaged: bool


class ProjectAutonomyState(BaseModel):
    """A project's autonomy default and kill switch, with any runs a kill switch action halted."""

    project_id: int
    default_level: str
    kill_switch_engaged: bool
    halted_run_ids: list[int] = []


class TaskGraphNode(BaseModel):
    """One buildable task in a project's plan graph, with its order and dependency relation.

    depends_on is the list of prerequisite task ids in the same project; sequence is the task's order
    in the walk; plan_unit_key links it to the plan unit it was sliced from. autonomy is the dial the
    slicer set (the project default, escalated when the unit is higher risk).
    """

    id: int
    title: str
    detail: str | None = None
    goal_for_agent: str | None = None
    status: str
    autonomy: str
    priority: str
    sequence: int | None = None
    depends_on: list[int] = []
    plan_unit_key: str | None = None
    run_id: int | None = None
    created_at: datetime
    updated_at: datetime | None = None


class TaskGraph(BaseModel):
    """A project's build task graph: the ordered generated tasks with their dependencies.

    plan_present reports whether the project carries a plan_json to slice. tasks are ordered by
    sequence so the orchestrator can walk them; depends_on on each node carries the relation.
    """

    project_id: int
    plan_present: bool
    count: int
    tasks: list[TaskGraphNode] = []


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
    # The autonomy gate decision recorded on the run: effective level, whether it auto advanced, and
    # the categories and reasons behind any escalation. Null on runs that predate the autonomy dial.
    autonomy: dict | None = None
    gate_step_id: int | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
