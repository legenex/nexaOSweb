"""agent run kind label for specialised runs (readiness)

Revision ID: 0014_agent_run_kind
Revises: 0013_journal_entries
Create Date: 2026-06-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_agent_run_kind"
down_revision: str | None = "0013_journal_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive: one nullable column on the existing agent_runs table. Nullable so existing rows
    # are untouched; the ORM default ("general") fills new rows and the read paths treat a null
    # as the default. An index supports filtering runs by kind (for example the readiness runs).
    op.add_column("agent_runs", sa.Column("kind", sa.String(length=40), nullable=True))
    op.create_index("ix_agent_runs_kind", "agent_runs", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_kind", table_name="agent_runs")
    op.drop_column("agent_runs", "kind")
