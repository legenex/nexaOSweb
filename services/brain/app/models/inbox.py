"""Intake and classification models."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class InboxItem(Base, TimestampMixin):
    __tablename__ = "inbox_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="note", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="captured", index=True, nullable=False)
    stage_history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class ClassificationRecord(Base, TimestampMixin):
    __tablename__ = "classification_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("inbox_items.id"), index=True, nullable=False
    )
    shape: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    recommended_route: Mapped[str] = mapped_column(String(60), nullable=False)
    recommended_model_key: Mapped[str] = mapped_column(String(60), nullable=False)
    resolved_model_id: Mapped[str] = mapped_column(String(160), nullable=False)
    model_rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reasoning_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class PipelineRun(Base, TimestampMixin):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("inbox_items.id"), index=True, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
