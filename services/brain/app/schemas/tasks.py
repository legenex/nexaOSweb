"""Task write schemas.

The read schema is TaskRead in app.schemas.entities, shared with the research finding to task
action. Create and update are defined here. status and source are validated in the router against
the canonical sets so a single source of truth governs both.
"""

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    detail: str | None = Field(default=None)
    # Optional link to a build project. The relationship is enforced in the router, not by a FK.
    project_id: int | None = None
    # Defaults to open on create; the client may set an initial status from the canonical set.
    status: str | None = Field(default=None, max_length=40)


class TaskUpdate(BaseModel):
    # Every field is optional; only the provided fields change. A null project_id detaches the
    # task from its project (clears the link); omit the field to leave it unchanged.
    title: str | None = Field(default=None, min_length=1, max_length=300)
    detail: str | None = Field(default=None)
    status: str | None = Field(default=None, max_length=40)
    project_id: int | None = None
