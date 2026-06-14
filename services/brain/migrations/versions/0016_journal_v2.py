"""journal v2: topics, attachments, and a nullable topic_id on entries

Revision ID: 0016_journal_v2
Revises: 0015_executor_workspace
Create Date: 2026-06-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_journal_v2"
down_revision: str | None = "0015_executor_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive only. Two new tables and one nullable column on the existing journal_notes table;
    # journal v1 is untouched. The new tables carry their foreign keys inside create_table, which
    # SQLite accepts since the constraints are part of the CREATE. topic_id is added as a plain
    # nullable column with no database level foreign key (SQLite cannot ALTER a constraint into an
    # existing table); the relationship to journal_topics is enforced in the ORM and the router.
    op.create_table(
        "journal_topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_journal_topics_user_id", "journal_topics", ["user_id"])

    op.create_table(
        "journal_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("note_id", sa.Integer(), sa.ForeignKey("journal_notes.id"), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("original_name", sa.String(length=300), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_journal_attachments_note_id", "journal_attachments", ["note_id"])

    op.add_column("journal_notes", sa.Column("topic_id", sa.Integer(), nullable=True))
    op.create_index("ix_journal_notes_topic_id", "journal_notes", ["topic_id"])


def downgrade() -> None:
    op.drop_index("ix_journal_notes_topic_id", table_name="journal_notes")
    op.drop_column("journal_notes", "topic_id")
    op.drop_index("ix_journal_attachments_note_id", table_name="journal_attachments")
    op.drop_table("journal_attachments")
    op.drop_index("ix_journal_topics_user_id", table_name="journal_topics")
    op.drop_table("journal_topics")
