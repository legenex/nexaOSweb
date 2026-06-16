"""deferred outcome seam: outcome_log

Revision ID: 0029_outcome_log
Revises: 0028_agent_audit
Create Date: 2026-06-16 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_outcome_log"
down_revision: str | None = "0028_agent_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive: one new table, no change to existing ones, no constraint drops. run_id and
    # project_id are plain columns with no database level foreign key (like tasks.run_id); the
    # relationship is enforced in the ORM and the writer. The unique index on run_id is created with
    # the table, which the SQLite dev target accepts as part of the CREATE. Per run usage and the
    # project budget need no schema: usage reuses existing storage, the budget lives in AppSetting.
    op.create_table(
        "outcome_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("reverted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outcome_log_run_id", "outcome_log", ["run_id"], unique=True)
    op.create_index("ix_outcome_log_project_id", "outcome_log", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_outcome_log_project_id", table_name="outcome_log")
    op.drop_index("ix_outcome_log_run_id", table_name="outcome_log")
    op.drop_table("outcome_log")
