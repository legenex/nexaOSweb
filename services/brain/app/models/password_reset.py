"""Password reset token model.

A reset request stores only the SHA-256 hash of the emailed token, never the raw token, so a
database leak cannot be replayed against the reset endpoint. Each row is single use (used_at) and
time limited (expires_at). The link delivered by email carries the raw token; the confirm endpoint
hashes the supplied token and looks the row up by that hash.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class PasswordResetToken(Base, TimestampMixin):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_password_reset_tokens_user_id"),
        index=True,
        nullable=False,
    )
    # SHA-256 hex digest of the raw token. Unique so a lookup is a single indexed hit.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Set the moment the token is spent, so a second confirm with the same link is rejected.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
