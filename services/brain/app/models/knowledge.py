"""Knowledge base entries.

A KnowledgeEntry is a single durable thing the system knows, entered by hand, consolidated by
the nightly Dreaming job, or imported from a connector. Entries are soft archived, never
deleted, so provenance and history stay intact.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, utcnow


class KnowledgeEntry(Base, TimestampMixin):
    __tablename__ = "knowledge_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # One of fact, preference, pattern, skill, rule, rejected_approach, recurring_correction.
    kind: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    # One of general, personal, development, work.
    scope: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    # One of manual, dreaming, connector.
    source: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    # One of active, archived. Archive is soft, the row is never deleted.
    status: Mapped[str] = mapped_column(String(40), default="active", index=True, nullable=False)
    # Where it came from, when, and by which job.
    provenance: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
