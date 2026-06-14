"""provider credentials and discovered models

Revision ID: 0018_models_connect
Revises: 0017_tasks_v2
Create Date: 2026-06-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_models_connect"
down_revision: str | None = "0017_tasks_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive only: two new tables, nothing existing is altered. provider_credentials records a
    # connected model provider by reference into the secret store (never the raw key) plus a non
    # secret last four hint. discovered_models caches the concrete models pulled live from a
    # connected provider, each with an enabled flag.
    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="available"),
        sa.Column("credentials_ref", sa.String(length=200), nullable=True),
        sa.Column("hint", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_provider_credentials_provider", "provider_credentials", ["provider"], unique=True
    )

    op.create_table(
        "discovered_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provider", "model_id", name="uq_discovered_models_provider_model"
        ),
    )
    op.create_index("ix_discovered_models_provider", "discovered_models", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_discovered_models_provider", table_name="discovered_models")
    op.drop_table("discovered_models")
    op.drop_index("ix_provider_credentials_provider", table_name="provider_credentials")
    op.drop_table("provider_credentials")
