"""Agent governance audit read schema.

The audit log is read only over HTTP. There is no write schema: rows are authored solely through
the writer in app/audit.py, and the table is append-only at the ORM. Each read is a pure
projection of a stored event.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    action: str
    actor_type: str
    actor: str
    reason: str
    project_id: int | None
    run_id: int | None
    step_id: int | None
    detail: dict[str, Any]
    created_at: datetime
