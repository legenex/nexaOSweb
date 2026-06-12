"""Dreaming consolidation models.

A MemoryCandidate is a proposed memory the nightly Dreaming job extracted from the day's
signals. It sits in a review queue as pending. Accepting it is the only path into the
Knowledge base. A DreamRun is the history record for one consolidation pass.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class MemoryCandidate(Base, TimestampMixin):
    __tablename__ = "memory_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # about_user or about_self.
    facet: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    # One of fact, preference, pattern, skill, rule, mirrors the knowledge kinds.
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    # One of general, personal, development, work, mirrors the knowledge scopes.
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    # Where the candidate came from, a list of {type, id, title} references.
    source_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # One of pending, accepted, dismissed.
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DreamRun(Base, TimestampMixin):
    __tablename__ = "dream_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # One of running, completed, failed.
    status: Mapped[str] = mapped_column(String(40), default="completed", nullable=False)
    # manual (dev trigger) or scheduled (nightly).
    trigger: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    # The semantic model key the extraction ran on, recorded for audit.
    model_key: Mapped[str] = mapped_column(String(60), default="bulk", nullable=False)
    items_considered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
