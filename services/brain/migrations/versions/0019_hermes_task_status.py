"""remap task status to the hermes board

Revision ID: 0019_hermes_task_status
Revises: 0018_models_connect
Create Date: 2026-06-15 00:00:00.000000

Data only, additive. The canonical task status set becomes the Hermes board: todo, doing,
agent_working, review, done (plus archived for soft hidden). Existing rows are remapped from
the prior set. No schema change.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019_hermes_task_status"
down_revision: str | None = "0018_models_connect"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # blocked is retained as a secondary status (Focus blocker bucket), only open and
    # in_progress are remapped onto the Hermes board.
    op.execute("UPDATE tasks SET status = 'todo' WHERE status = 'open'")
    op.execute("UPDATE tasks SET status = 'doing' WHERE status = 'in_progress'")


def downgrade() -> None:
    op.execute("UPDATE tasks SET status = 'open' WHERE status = 'todo'")
    op.execute("UPDATE tasks SET status = 'in_progress' WHERE status = 'doing'")
