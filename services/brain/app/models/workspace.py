"""Workspace models present from the data layer so later tabs can grow."""

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, utcnow


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # Optional longer description, shown as Notes in the task dialog; the title stays the one line
    # summary. There is no separate notes column: detail is the notes field.
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # What the user wants an agent to achieve with this task, free text, optional. Distinct from
    # detail: detail describes the task, goal_for_agent is the instruction handed to a run.
    goal_for_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A loose human timeline, free text (for example "this week"), not a hard schedule.
    timeline: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # low, med, or high. Validated in the router; defaults to med.
    priority: Mapped[str] = mapped_column(String(10), default="med", nullable=False)
    # Optional hard due date (calendar date, no time).
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Ordering within a board column. A drag sets status plus position; lists order by position.
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Card checklist: a JSON array of {id, text, done}. The board card shows the done count.
    checklist: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Card labels: a JSON array of {name, color}, color from the brand palette (validated in the
    # router). Shown as pills on the card face.
    labels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Hermes board: todo, doing, agent_working, review, done (plus archived). Validated in the
    # router. agent_working is also surfaced for a task whose run is live.
    status: Mapped[str] = mapped_column(String(40), default="todo", nullable=False)
    # How the task was created: manual (the user), research (a research finding), or run (an
    # agent run). Validated in the router; defaults to manual for hand created tasks.
    source: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    # A seam to the agent run that produced this task, when one did. A plain nullable column with
    # no database level foreign key (added to the existing table on the SQLite dev target); the
    # relationship to agent_runs is enforced in the router, like JournalNote.topic_id.
    run_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # Soft delete marker: a deleted task keeps its row and stays recoverable, and is excluded
    # from default lists and from the open task counts on the Dashboard and Insights.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=True
    )


class TaskComment(Base, TimestampMixin):
    """A comment on a task's activity thread. Soft deleted like the rest of the workspace."""

    __tablename__ = "task_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True, nullable=False)
    # The author, nullable so a comment survives if the user row is ever detached.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JournalNote(Base, TimestampMixin):
    __tablename__ = "journal_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Optional mood label and freeform tags for an entry.
    mood: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # The topic this entry groups under, or null for an untopiced entry. A plain column with no
    # database level foreign key (added to the existing table on the SQLite dev target); the
    # relationship to journal_topics is enforced in the router, like Project.research_target_id.
    topic_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # Soft delete marker: a deleted entry keeps its row and stays recoverable, and is excluded
    # from default lists and from the Dreaming input.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class JournalTopic(Base, TimestampMixin):
    """A user created grouping for journal entries (for example Personal, Work, Thoughts).

    User scoped, seeded with none: the user creates topics. Soft deleted, never hard deleted; on
    delete its entries fall back to untopiced (their topic_id is cleared) and are kept.
    """

    __tablename__ = "journal_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JournalAttachment(Base, TimestampMixin):
    """A file or image attached to a journal entry.

    The bytes are stored under NEXA_UPLOADS_ROOT through the path safety gate; the row keeps only
    the relative path, the original file name, and the kind. Soft deleted, never hard deleted: a
    deleted attachment keeps its row (and its file) and is excluded from default lists.
    """

    __tablename__ = "journal_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("journal_notes.id"), index=True, nullable=False
    )
    # One of image or file.
    kind: Mapped[str] = mapped_column(String(20), default="file", nullable=False)
    # Relative path under the uploads root, never an absolute or escaping path.
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    key: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
