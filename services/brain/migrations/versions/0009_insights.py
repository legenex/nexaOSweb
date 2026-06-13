"""insight runs and insights

Revision ID: 0009_insights
Revises: 0008_project_modes
Create Date: 2026-06-13 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_insights"
down_revision: str | None = "0008_project_modes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "insight_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("trigger", sa.String(length=40), nullable=False),
        sa.Column("extraction_model_key", sa.String(length=60), nullable=False),
        sa.Column("synthesis_model_key", sa.String(length=60), nullable=False),
        sa.Column("insights_created", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_insight_runs_user_id", "insight_runs", ["user_id"])

    op.create_table(
        "insights",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("insight_runs.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("idea_kind", sa.String(length=40), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=60), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("action_ref", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_insights_run_id", "insights", ["run_id"])
    op.create_index("ix_insights_user_id", "insights", ["user_id"])
    op.create_index("ix_insights_category", "insights", ["category"])
    op.create_index("ix_insights_status", "insights", ["status"])


def downgrade() -> None:
    op.drop_table("insights")
    op.drop_table("insight_runs")
