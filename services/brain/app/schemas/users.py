"""User management request and read schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr

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


class UserInvite(BaseModel):
    email: EmailStr
    name: str | None = None
    role: UserRole = "member"


class UserUpdate(BaseModel):
    """Change a user's role, display name, or status. Only supplied fields change."""

    role: UserRole | None = None
    name: str | None = None
    status: UserStatus | None = None


class ProfileUpdate(BaseModel):
    """Self profile edit from Settings, General."""

    name: str | None = None
