"""Insight models.

An Insight is a derived observation about the user or the work, generated from the Knowledge
base and recent activity. Insights are grouped into four categories: personal patterns, work
patterns, a generative profile summary, and an innovation feed of ideas. Each carries a
confidence, a source, and a short reasoning summary, and supports actions (save to knowledge,
create task, create project, dismiss). Generation runs in batches recorded as an InsightRun so
the latest batch can be cached and refreshed on demand. Rows are never deleted; a refresh
supersedes the prior active batch.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class InsightRun(Base, TimestampMixin):
    __tablename__ = "insight_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    # running, completed, or failed.
    status: Mapped[str] = mapped_column(String(40), default="completed", nullable=False)
    # lazy (first read) or manual (explicit refresh).
    trigger: Mapped[str] = mapped_column(String(40), default="lazy", nullable=False)
    # Semantic keys the two passes ran on, recorded for audit. Extraction is bulk, the
    # final pass is research_synthesis.
    extraction_model_key: Mapped[str] = mapped_column(String(60), default="bulk", nullable=False)
    synthesis_model_key: Mapped[str] = mapped_column(
        String(60), default="research_synthesis", nullable=False
    )
    insights_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Insight(Base, TimestampMixin):
    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("insight_runs.id"), index=True, nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    # personal_pattern, work_pattern, profile_summary, or innovation.
    category: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    # For innovation feed entries: project, revenue, or automation. Null otherwise.
    idea_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    # Where it was derived from: knowledge, activity, or knowledge+activity.
    source: Mapped[str] = mapped_column(String(60), default="activity", nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Underlying references, a list of {type, id, title}.
    source_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # active, saved, tasked, project_created, dismissed, or superseded.
    status: Mapped[str] = mapped_column(String(40), default="active", index=True, nullable=False)
    # The entity an action created, for example {type, id}.
    action_ref: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
