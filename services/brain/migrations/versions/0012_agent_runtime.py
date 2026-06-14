"""agent runtime spine: agent_runs and agent_steps

Revision ID: 0012_agent_runtime
Revises: 0011_research_config
Create Date: 2026-06-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_agent_runtime"
down_revision: str | None = "0011_research_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive: two new tables, no change to existing ones. The self referential parent_run_id
    # and the pm_run_id link are declared inside create_table, which SQLite accepts since the
    # constraints are part of the CREATE rather than an ALTER. cursor_step_id is a plain column
    # with no database level foreign key, to avoid a circular constraint with agent_steps; the
    # relationship is enforced in the ORM and router instead.
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("autonomy_level", sa.Integer(), nullable=False),
        sa.Column("branch_ref", sa.String(length=300), nullable=True),
        sa.Column("cursor_step_id", sa.Integer(), nullable=True),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("goal_summary", sa.Text(), nullable=False),
        sa.Column("context_summary", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("proposed_by", sa.String(length=40), nullable=False),
        sa.Column("parent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("pm_run_id", sa.Integer(), sa.ForeignKey("pm_runs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_parent_run_id", "agent_runs", ["parent_run_id"])
    op.create_index("ix_agent_runs_pm_run_id", "agent_runs", ["pm_run_id"])

    op.create_table(
        "agent_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("proposed_by", sa.String(length=40), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("tool_call", sa.JSON(), nullable=True),
        sa.Column("failure", sa.JSON(), nullable=True),
        sa.Column("approval", sa.JSON(), nullable=True),
        sa.Column("correction_note", sa.Text(), nullable=True),
        sa.Column("corrected_from", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_steps_run_id", "agent_steps", ["run_id"])
    op.create_index("ix_agent_steps_status", "agent_steps", ["status"])
    op.create_index("ix_agent_steps_run_id_seq", "agent_steps", ["run_id", "seq"])


def downgrade() -> None:
    op.drop_table("agent_steps")
    op.drop_table("agent_runs")
