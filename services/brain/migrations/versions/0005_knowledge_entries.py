"""knowledge entries

Revision ID: 0005_knowledge_entries
Revises: 0004_project_item_unique
Create Date: 2026-06-12 00:04:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_knowledge_entries"
down_revision: str | None = "0004_project_item_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_entries_kind", "knowledge_entries", ["kind"])
    op.create_index("ix_knowledge_entries_scope", "knowledge_entries", ["scope"])
    op.create_index("ix_knowledge_entries_source", "knowledge_entries", ["source"])
    op.create_index("ix_knowledge_entries_status", "knowledge_entries", ["status"])


def downgrade() -> None:
    op.drop_table("knowledge_entries")
