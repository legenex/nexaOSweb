"""task graph from the plan slicer: sequence, depends_on, and the generated-from-plan link

Revision ID: 0026_task_slicer_graph
Revises: 0025_autonomy_gating
Create Date: 2026-06-16 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_task_slicer_graph"
down_revision: str | None = "0025_autonomy_gating"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive only: three nullable columns on the existing tasks table, no constraints, so a plain
    # add_column is safe on the SQLite dev target. A hand created task leaves all three null; a task
    # the plan slicer generated carries a sequence index, a JSON list of prerequisite task ids in
    # depends_on, and a plan_unit_key that links it back to the plan unit it was sliced from. There is
    # no database level foreign key for depends_on (the dev target is SQLite, which cannot add a
    # constraint to an existing table); the relationship is held in the ORM and validated in the
    # router, exactly like tasks.run_id and projects research links.
    op.add_column("tasks", sa.Column("sequence", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("depends_on", sa.JSON(), nullable=True))
    op.add_column("tasks", sa.Column("plan_unit_key", sa.String(length=200), nullable=True))
    op.create_index("ix_tasks_plan_unit_key", "tasks", ["plan_unit_key"])


def downgrade() -> None:
    op.drop_index("ix_tasks_plan_unit_key", table_name="tasks")
    op.drop_column("tasks", "plan_unit_key")
    op.drop_column("tasks", "depends_on")
    op.drop_column("tasks", "sequence")
