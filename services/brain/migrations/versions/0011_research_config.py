"""research project config and run analysis fields

Revision ID: 0011_research_config
Revises: 0010_user_roles
Create Date: 2026-06-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_research_config"
down_revision: str | None = "0010_user_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive JSON columns. Nullable so existing rows are untouched; the ORM default fills new
    # rows, and the read paths treat a null as the empty value.
    op.add_column("projects", sa.Column("research_config", sa.JSON(), nullable=True))
    op.add_column("research_runs", sa.Column("analysis", sa.Text(), nullable=True))
    op.add_column("research_runs", sa.Column("key_takeaways", sa.JSON(), nullable=True))
    op.add_column("research_runs", sa.Column("suggestions", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("research_runs", "suggestions")
    op.drop_column("research_runs", "key_takeaways")
    op.drop_column("research_runs", "analysis")
    op.drop_column("projects", "research_config")
