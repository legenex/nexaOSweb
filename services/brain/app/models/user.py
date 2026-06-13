"""User model."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Display name shown in the profile footer and the Users list.
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # owner, admin, or member. The earliest user is the owner.
    role: Mapped[str] = mapped_column(String(40), default="member", nullable=False)
    # active, invited (created by an invite, no password set yet), or removed (soft delete).
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
