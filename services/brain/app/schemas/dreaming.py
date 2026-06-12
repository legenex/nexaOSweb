"""Dreaming request and read schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

MemoryFacet = Literal["about_user", "about_self"]
CandidateStatus = Literal["pending", "accepted", "dismissed"]
DreamTrigger = Literal["manual", "scheduled"]


class MemoryCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    facet: str
    kind: str
    scope: str
    content: str
    confidence: float
    source_refs: list[Any]
    status: str
    created_at: datetime
    reviewed_at: datetime | None


class DreamRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    trigger: str
    model_key: str
    items_considered: int
    candidates_created: int
    created_at: datetime
    finished_at: datetime | None
