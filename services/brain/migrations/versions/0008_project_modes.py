"""project mode, workspace metadata, updated_at, and the build log

Revision ID: 0008_project_modes
Revises: 0007_research_link
Create Date: 2026-06-13 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_project_modes"
down_revision: str | None = "0007_research_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive columns on projects. Server defaults backfill existing rows; the ORM owns
    # the value going forward. mode and workspace use constant defaults. updated_at uses a
    # constant placeholder default (not func.now) because SQLite, the dev target, rejects a
    # non constant default on a NOT NULL ADD COLUMN; existing rows are then backfilled from
    # created_at. Postgres accepts the same constant default.
    op.add_column(
        "projects",
        sa.Column("mode", sa.String(length=40), nullable=False, server_default="app"),
    )
    op.add_column(
        "projects",
        sa.Column("workspace", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "projects",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("'1970-01-01 00:00:00'"),
        ),
    )
    op.execute("UPDATE projects SET updated_at = created_at")

    op.create_table(
        "build_log_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.String(length=400), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("diff_summary", sa.Text(), nullable=False),
        sa.Column("before_content", sa.Text(), nullable=True),
        sa.Column("after_content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_build_log_entries_project_id", "build_log_entries", ["project_id"]
    )
    op.create_index("ix_build_log_entries_status", "build_log_entries", ["status"])


def downgrade() -> None:
    op.drop_table("build_log_entries")
    op.drop_column("projects", "updated_at")
    op.drop_column("projects", "workspace")
    op.drop_column("projects", "mode")
