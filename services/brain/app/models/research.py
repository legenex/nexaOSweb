"""Research models: the project Update Log, research runs, and research findings.

A research project can attach to a build project (Project.research_target_id). When a research
run completes, each finding is posted as a ProjectUpdate in the attached build project's
Update Log. Findings can also be converted into a task, a project update, or saved to the
Knowledge base.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ProjectUpdate(Base, TimestampMixin):
    __tablename__ = "project_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=False
    )
    # research_finding, manual, or system.
    kind: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Where the entry came from, for example {type, finding_id, research_project_id, run_id}.
    source_ref: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ResearchRun(Base, TimestampMixin):
    __tablename__ = "research_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=False
    )
    # running, completed, or failed.
    status: Mapped[str] = mapped_column(String(40), default="completed", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    findings_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchFinding(Base, TimestampMixin):
    __tablename__ = "research_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The research project that produced this finding.
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=False
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_runs.id"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    url: Mapped[str | None] = mapped_column(String(600), nullable=True)
    # new, tasked, logged, or saved, set by the finding level actions.
    status: Mapped[str] = mapped_column(String(40), default="new", index=True, nullable=False)
