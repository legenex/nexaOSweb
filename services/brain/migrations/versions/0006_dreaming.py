"""dreaming consolidation

Revision ID: 0006_dreaming
Revises: 0005_knowledge_entries
Create Date: 2026-06-12 00:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_dreaming"
down_revision: str | None = "0005_knowledge_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("facet", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_memory_candidates_facet", "memory_candidates", ["facet"])
    op.create_index("ix_memory_candidates_status", "memory_candidates", ["status"])

    op.create_table(
        "dream_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("trigger", sa.String(length=40), nullable=False),
        sa.Column("model_key", sa.String(length=60), nullable=False),
        sa.Column("items_considered", sa.Integer(), nullable=False),
        sa.Column("candidates_created", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("dream_runs")
    op.drop_table("memory_candidates")
