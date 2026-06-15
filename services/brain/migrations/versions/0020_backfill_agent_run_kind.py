"""backfill null agent_run kind

Revision ID: 0020_backfill_agent_run_kind
Revises: 0019_hermes_task_status
Create Date: 2026-06-15 00:10:00.000000

Data only, additive. A legacy run row carried kind NULL (created before the column had its
default), which broke RunRead serialization and 500'd the runtime list. Backfill those to the
model default so the contract holds.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020_backfill_agent_run_kind"
down_revision: str | None = "0019_hermes_task_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE agent_runs SET kind = 'general' WHERE kind IS NULL")


def downgrade() -> None:
    pass
