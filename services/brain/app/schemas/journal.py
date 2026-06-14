"""Journal schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TranscribeResponse(BaseModel):
    transcript: str


class JournalEntryCreate(BaseModel):
    body: str = Field(min_length=1)
    mood: str | None = Field(default=None, max_length=40)
    tags: list[str] = Field(default_factory=list)


class JournalEntryUpdate(BaseModel):
    body: str | None = Field(default=None, min_length=1)
    mood: str | None = Field(default=None, max_length=40)
    tags: list[str] | None = None


class JournalEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    body: str
    mood: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime | None
