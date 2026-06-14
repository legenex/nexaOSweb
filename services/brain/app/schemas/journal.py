"""Journal schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TranscribeResponse(BaseModel):
    transcript: str


class CaptureResponse(BaseModel):
    """The transcribed text of a handwritten page, plus the vision model that produced it."""

    text: str
    model: str


class JournalEntryCreate(BaseModel):
    body: str = Field(min_length=1)
    mood: str | None = Field(default=None, max_length=40)
    tags: list[str] = Field(default_factory=list)
    topic_id: int | None = None


class JournalEntryUpdate(BaseModel):
    body: str | None = Field(default=None, min_length=1)
    mood: str | None = Field(default=None, max_length=40)
    tags: list[str] | None = None
    # topic_id is updatable: 0 or a negative id is rejected by the router; null leaves it unchanged
    # on update, so untopicing is done by deleting the topic or via a dedicated move (not here).
    topic_id: int | None = None


class JournalEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    body: str
    mood: str | None
    tags: list[str]
    topic_id: int | None
    created_at: datetime
    updated_at: datetime | None


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TopicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    note_id: int
    kind: str
    original_name: str
    created_at: datetime


class IngestRequest(BaseModel):
    """An inbound journal entry from an external source, authenticated by a per source token.

    The token authenticates the source and is never stored on the entry. The body becomes the
    entry text; the source is recorded as a tag so the origin is traceable.
    """

    source: str = Field(min_length=1, max_length=80)
    token: str = Field(min_length=1)
    body: str = Field(min_length=1)
    mood: str | None = Field(default=None, max_length=40)
    tags: list[str] = Field(default_factory=list)
