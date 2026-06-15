"""task board fields

Revision ID: 0022_task_board_fields
Revises: 0021_password_reset_tokens
Create Date: 2026-06-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_task_board_fields"
down_revision: str | None = "0021_password_reset_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive only: five new columns on the existing tasks table, no constraints, so a plain
    # add_column is safe on the SQLite dev target. Server defaults backfill existing rows so the
    # not-null priority and position columns are valid for tasks that predate this change.
    op.add_column("tasks", sa.Column("goal_for_agent", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("timeline", sa.String(length=120), nullable=True))
    op.add_column(
        "tasks",
        sa.Column("priority", sa.String(length=10), nullable=False, server_default="med"),
    )
    op.add_column("tasks", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("tasks", "position")
    op.drop_column("tasks", "due_date")
    op.drop_column("tasks", "priority")
    op.drop_column("tasks", "timeline")
    op.drop_column("tasks", "goal_for_agent")
