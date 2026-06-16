"""autonomy dial on tasks, and project autonomy default plus kill switch

Revision ID: 0025_autonomy_gating
Revises: 0024_agent_build_run
Create Date: 2026-06-16 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_autonomy_gating"
down_revision: str | None = "0024_agent_build_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive only: one column on tasks and two on projects, no constraints, so a plain add_column is
    # safe on the SQLite dev target. Server defaults backfill existing rows so the not-null columns are
    # valid for tasks and projects that predate the autonomy dial. yellow is the safe default level
    # (pause at the gate), and the kill switch starts released.
    op.add_column(
        "tasks",
        sa.Column("autonomy", sa.String(length=10), nullable=False, server_default="yellow"),
    )
    op.add_column(
        "projects",
        sa.Column(
            "agent_autonomy_default",
            sa.String(length=10),
            nullable=False,
            server_default="yellow",
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "agent_kill_switch",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "agent_kill_switch")
    op.drop_column("projects", "agent_autonomy_default")
    op.drop_column("tasks", "autonomy")
