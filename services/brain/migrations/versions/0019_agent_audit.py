"""agent governance audit log: agent_audit

Revision ID: 0019_agent_audit
Revises: 0018_models_connect
Create Date: 2026-06-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_agent_audit"
down_revision: str | None = "0018_models_connect"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive: one new table, no change to existing ones, no constraint drops. project_id and
    # run_id are plain indexed columns with no database level foreign key (like tasks.run_id), so
    # the append-only log is never blocked or cascaded by the rows it describes; the scoping
    # relationship is enforced in the router. The table is append-only at the ORM (two mapper
    # listeners refuse UPDATE and DELETE), so there is no soft delete column to add.
    op.create_table(
        "agent_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("step_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_audit_category", "agent_audit", ["category"])
    op.create_index("ix_agent_audit_actor", "agent_audit", ["actor"])
    op.create_index("ix_agent_audit_project_id", "agent_audit", ["project_id"])
    op.create_index("ix_agent_audit_run_id", "agent_audit", ["run_id"])
    op.create_index("ix_agent_audit_created_at", "agent_audit", ["created_at"])


def downgrade() -> None:
    op.drop_table("agent_audit")
