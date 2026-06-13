"""user name, role, and status

Revision ID: 0010_user_roles
Revises: 0009_insights
Create Date: 2026-06-13 03:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_user_roles"
down_revision: str | None = "0009_insights"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive columns with constant server defaults so existing rows backfill cleanly on both
    # SQLite (dev) and Postgres (prod). The earliest user is promoted to owner afterwards.
    op.add_column("users", sa.Column("name", sa.String(length=200), nullable=True))
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=40), nullable=False, server_default="member"),
    )
    op.add_column(
        "users",
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
    )
    op.execute("UPDATE users SET role = 'owner' WHERE id = (SELECT MIN(id) FROM users)")


def downgrade() -> None:
    op.drop_column("users", "status")
    op.drop_column("users", "role")
    op.drop_column("users", "name")
