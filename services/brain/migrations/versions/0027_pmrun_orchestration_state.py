"""orchestrator loop audit and progress state on the pm run

Revision ID: 0027_pmrun_orchestration_state
Revises: 0026_task_slicer_graph
Create Date: 2026-06-16 03:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_pmrun_orchestration_state"
down_revision: str | None = "0026_task_slicer_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive only: one JSON column on the existing pm_runs table, no constraints, so a plain
    # add_column is safe on the SQLite dev target. The orchestrator records its loop audit (dispatches,
    # gate decisions, pauses, the run cap and budget, and why it stopped) here. A server default of an
    # empty object backfills existing pm run rows so the not-null column is valid for them.
    op.add_column(
        "pm_runs",
        sa.Column("state", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("pm_runs", "state")
