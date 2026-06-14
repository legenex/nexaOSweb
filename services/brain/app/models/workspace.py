"""Workspace models present from the data layer so later tabs can grow."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
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
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)


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
