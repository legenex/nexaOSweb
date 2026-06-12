"""baseline

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-12 00:00:00.000000
"""

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Empty baseline. Tables are introduced by later additive migrations.
    pass


def downgrade() -> None:
    pass
