"""Task write schemas.

The read schema is TaskRead in app.schemas.entities, shared with the research finding to task
action. Create and update are defined here. status, source, and priority are validated in the
router against the canonical sets so a single source of truth governs both. detail doubles as the
Notes field shown in the task dialog; there is no separate notes field.
"""

from datetime import date

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    detail: str | None = Field(default=None)
    # What the user wants an agent to achieve with this task, free text.
    goal_for_agent: str | None = Field(default=None)
    # A loose human timeline, free text (for example "this week").
    timeline: str | None = Field(default=None, max_length=120)
    # Optional link to a build project. The relationship is enforced in the router, not by a FK.
    project_id: int | None = None
    # Defaults to todo on create; the client may set an initial status from the canonical set.
    status: str | None = Field(default=None, max_length=40)
    # low, med, or high. Defaults to med in the router when omitted; validated there.
    priority: str | None = Field(default=None, max_length=10)
    due_date: date | None = None


class TaskUpdate(BaseModel):
    # Every field is optional; only the provided fields change. A null project_id detaches the
    # task from its project (clears the link); omit the field to leave it unchanged.
    title: str | None = Field(default=None, min_length=1, max_length=300)
    detail: str | None = Field(default=None)
    goal_for_agent: str | None = Field(default=None)
    timeline: str | None = Field(default=None, max_length=120)
    status: str | None = Field(default=None, max_length=40)
    priority: str | None = Field(default=None, max_length=10)
    project_id: int | None = None
    due_date: date | None = None
    # Ordering within a column; a drag and drop sets status plus position together.
    position: int | None = None


class TaskDraftRequest(BaseModel):
    # A short title or rough description the AI expands into a structured draft.
    prompt: str = Field(min_length=1, max_length=2000)


class TaskDraft(BaseModel):
    # A draft for the dialog to fill. It is not a task; the human reviews and adds it.
    title: str
    notes: str
    goal_for_agent: str
    priority: str
    timeline: str
