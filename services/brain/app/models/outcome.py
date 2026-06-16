"""The deferred outcome seam: OutcomeLog.

One row per completed build run records the human verdict on the run (approved or rejected),
whether a merged change was later reverted, and a free text note. This is the recording seam only.
No ranking, scoring, or learning is built on it now; that is a deferred milestone (see
docs/ARCHITECTURE.md). Capturing the outcomes durably from day one is what makes the later learning
possible without a backfill.

run_id and project_id are plain indexed columns with no database level foreign key (like
tasks.run_id), so the log is independent of the rows it describes. There is at most one row per run;
the writer in app/outcomes.py upserts by run_id, and a later revert sets reverted on the existing
row rather than adding a second one.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, utcnow


class OutcomeLog(Base, TimestampMixin):
    __tablename__ = "outcome_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The run whose outcome this records. Unique: one outcome row per run, enforced by the writer
    # and the unique index created with the table.
    run_id: Mapped[int] = mapped_column(Integer, index=True, unique=True, nullable=False)
    project_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # The human verdict that disposed of the run: approved (the diff merged) or rejected (dropped).
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    # Whether a merged change was later reverted. Sticky once set: a revert never un-reverts.
    reverted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # A free text note from the resolver, optional.
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
