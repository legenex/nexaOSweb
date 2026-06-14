"""User management request and read schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

UserRole = Literal["owner", "admin", "member"]
UserStatus = Literal["active", "invited", "removed"]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str | None
    role: str
    status: str
    created_at: datetime


class UserCreate(BaseModel):
    """Directly provision an active, ready to log in user with a password set.

    This is the owner path for adding people without an email invite round trip. The created
    user is active immediately, so they can sign in with the supplied password.
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: str | None = None
    role: UserRole = "member"


class UserInvite(BaseModel):
    email: EmailStr
    name: str | None = None
    role: UserRole = "member"


class UserUpdate(BaseModel):
    """Change a user's role, display name, status, or password. Only supplied fields change.

    Setting a password on an invited user makes the account usable, so the server also flips
    such a user to active when a password is provided.
    """

    role: UserRole | None = None
    name: str | None = None
    status: UserStatus | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


class ProfileUpdate(BaseModel):
    """Self profile edit from Settings, General."""

    name: str | None = None
