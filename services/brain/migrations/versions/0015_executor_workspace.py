"""executor phase a seams: worktree and phase on runs, idempotency key on steps

Revision ID: 0015_executor_workspace
Revises: 0014_agent_run_kind
Create Date: 2026-06-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_executor_workspace"
down_revision: str | None = "0014_agent_run_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive only. Three nullable columns on the existing runtime tables, never a rewrite. The
    # executor populates worktree_path and phase on its own runs; every existing run keeps them
    # null. idempotency_key is null on every existing step.
    op.add_column("agent_runs", sa.Column("worktree_path", sa.String(length=500), nullable=True))
    op.add_column("agent_runs", sa.Column("phase", sa.String(length=40), nullable=True))
    op.add_column(
        "agent_steps", sa.Column("idempotency_key", sa.String(length=200), nullable=True)
    )
    # Unique per run, not globally: the index is over (run_id, idempotency_key). It is created
    # with create_index (not an ALTER that adds a table constraint), so SQLite accepts it on the
    # existing table. SQLite and Postgres both treat nulls as distinct, so the many steps that
    # carry no key never collide.
    op.create_index(
        "uq_agent_steps_run_idempotency_key",
        "agent_steps",
        ["run_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_agent_steps_run_idempotency_key", table_name="agent_steps")
    op.drop_column("agent_steps", "idempotency_key")
    op.drop_column("agent_runs", "phase")
    op.drop_column("agent_runs", "worktree_path")
