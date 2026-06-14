"""journal entry fields: mood, tags, soft delete, updated_at

Revision ID: 0013_journal_entries
Revises: 0012_agent_runtime
Create Date: 2026-06-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_journal_entries"
down_revision: str | None = "0012_agent_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive columns on the existing journal_notes table. Nullable so existing rows are
    # untouched; the ORM defaults fill new rows and the read paths treat a null as the default.
    op.add_column("journal_notes", sa.Column("mood", sa.String(length=40), nullable=True))
    op.add_column("journal_notes", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column(
        "journal_notes", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "journal_notes", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("journal_notes", "updated_at")
    op.drop_column("journal_notes", "deleted_at")
    op.drop_column("journal_notes", "tags")
    op.drop_column("journal_notes", "mood")
