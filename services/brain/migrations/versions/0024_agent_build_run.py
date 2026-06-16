"""agent build engine: backend, reasoning summary, cost, and task link on runs

Revision ID: 0024_agent_build_run
Revises: 0023_task_card_detail
Create Date: 2026-06-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_agent_build_run"
down_revision: str | None = "0023_task_card_detail"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive only. Four nullable columns on the existing agent_runs table, never a rewrite. A
    # build engine run is an executor-kind run discriminated by a non-null backend; every existing
    # run keeps all four null. task_id is a plain column with no database level foreign key (the
    # dev target is SQLite, which cannot add a constraint to an existing table); the relationship to
    # tasks is enforced in the ORM and the router, exactly like tasks.run_id points back here.
    op.add_column("agent_runs", sa.Column("backend", sa.String(length=40), nullable=True))
    op.add_column("agent_runs", sa.Column("reasoning_summary", sa.Text(), nullable=True))
    op.add_column("agent_runs", sa.Column("cost_usd", sa.Float(), nullable=True))
    op.add_column("agent_runs", sa.Column("task_id", sa.Integer(), nullable=True))
    op.create_index("ix_agent_runs_task_id", "agent_runs", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_task_id", table_name="agent_runs")
    op.drop_column("agent_runs", "task_id")
    op.drop_column("agent_runs", "cost_usd")
    op.drop_column("agent_runs", "reasoning_summary")
    op.drop_column("agent_runs", "backend")
