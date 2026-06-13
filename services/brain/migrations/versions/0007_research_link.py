"""research to project link, update log, runs, findings

Revision ID: 0007_research_link
Revises: 0006_dreaming
Create Date: 2026-06-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_research_link"
down_revision: str | None = "0006_dreaming"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive column: a research project points at the build project it feeds. The DB level
    # foreign key is omitted because SQLite cannot ALTER in a constraint on an existing table;
    # the ORM model declares the relationship and the router validates the target exists.
    op.add_column(
        "projects",
        sa.Column("research_target_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_projects_research_target_id", "projects", ["research_target_id"])

    op.create_table(
        "project_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_updates_project_id", "project_updates", ["project_id"])

    op.create_table(
        "research_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("findings_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_research_runs_project_id", "research_runs", ["project_id"])

    op.create_table(
        "research_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("research_runs.id"), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=600), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_research_findings_project_id", "research_findings", ["project_id"])
    op.create_index("ix_research_findings_run_id", "research_findings", ["run_id"])
    op.create_index("ix_research_findings_status", "research_findings", ["status"])


def downgrade() -> None:
    op.drop_table("research_findings")
    op.drop_table("research_runs")
    op.drop_table("project_updates")
    op.drop_index("ix_projects_research_target_id", table_name="projects")
    op.drop_column("projects", "research_target_id")
