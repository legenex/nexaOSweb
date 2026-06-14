"""Knowledge base request and read schemas.

The five enums are enforced as Literal types so the OpenAPI documents the allowed values and
the client gets them for free. Confidence is constrained to the zero to one range.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

KnowledgeKind = Literal[
    "fact",
    "preference",
    "pattern",
    "skill",
    "rule",
    # First-class memory of how the agent should behave, surfaced in the personal memory view:
    # an approach the user rejected, and a correction the user has had to make more than once.
    "rejected_approach",
    "recurring_correction",
]
KnowledgeScope = Literal["general", "personal", "development", "work"]
KnowledgeSource = Literal["manual", "dreaming", "connector"]
KnowledgeStatus = Literal["active", "archived"]


class KnowledgeEntryCreate(BaseModel):
    kind: KnowledgeKind
    scope: KnowledgeScope
    source: KnowledgeSource = "manual"
    content: str = Field(min_length=1)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    status: KnowledgeStatus = "active"
    provenance: dict[str, Any] = Field(default_factory=dict)


class KnowledgeEntryUpdate(BaseModel):
    """Partial update. Only the supplied fields change. Archiving has its own endpoint."""

    kind: KnowledgeKind | None = None
    scope: KnowledgeScope | None = None
    source: KnowledgeSource | None = None
    content: str | None = Field(default=None, min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: KnowledgeStatus | None = None
    provenance: dict[str, Any] | None = None


class KnowledgeEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    scope: str
    source: str
    content: str
    confidence: float
    status: str
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime
