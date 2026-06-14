"""tasks v2: detail, source, run_id seam, soft delete, and updated_at

Revision ID: 0017_tasks_v2
Revises: 0016_journal_v2
Create Date: 2026-06-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_tasks_v2"
down_revision: str | None = "0016_journal_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive only. Five new nullable columns on the existing tasks table; the existing id,
    # user_id, project_id, title, status, and created_at are untouched. source carries a server
    # default of manual so existing rows are backfilled. run_id is a plain nullable column with no
    # database level foreign key (SQLite cannot ALTER a constraint into an existing table); the
    # relationship to agent_runs is enforced in the ORM and the router.
    op.add_column("tasks", sa.Column("detail", sa.Text(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column("source", sa.String(length=40), nullable=False, server_default="manual"),
    )
    op.add_column("tasks", sa.Column("run_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_tasks_run_id", "tasks", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_run_id", table_name="tasks")
    op.drop_column("tasks", "updated_at")
    op.drop_column("tasks", "deleted_at")
    op.drop_column("tasks", "run_id")
    op.drop_column("tasks", "source")
    op.drop_column("tasks", "detail")
