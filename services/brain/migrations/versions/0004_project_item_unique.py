"""unique project per item

Revision ID: 0004_project_item_unique
Revises: 0003_core_models
Create Date: 2026-06-12 00:03:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_project_item_unique"
down_revision: str | None = "0003_core_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One project per inbox item. Container projects (item_id NULL) are unaffected because
    # a unique index permits multiple NULLs.
    op.create_index(
        "uq_projects_item_id", "projects", ["item_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_projects_item_id", table_name="projects")
