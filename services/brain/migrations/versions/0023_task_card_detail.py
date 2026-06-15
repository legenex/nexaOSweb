"""task card detail: checklists, labels, comments

Revision ID: 0023_task_card_detail
Revises: 0022_task_board_fields
Create Date: 2026-06-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_task_card_detail"
down_revision: str | None = "0022_task_board_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive only. checklist and labels are JSON arrays on the task; an empty array default
    # backfills existing rows. task_comments is a new table for the card activity thread, with the
    # foreign keys declared in create_table (allowed for a brand new table on SQLite).
    op.add_column(
        "tasks",
        sa.Column("checklist", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "tasks",
        sa.Column("labels", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.create_table(
        "task_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_task_comments_task_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_task_comments_user_id"),
    )
    op.create_index("ix_task_comments_task_id", "task_comments", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_task_comments_task_id", table_name="task_comments")
    op.drop_table("task_comments")
    op.drop_column("tasks", "labels")
    op.drop_column("tasks", "checklist")
