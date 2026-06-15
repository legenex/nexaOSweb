"""Auth schemas."""

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    # Same minimum as the user management password rules so a reset cannot set a weaker password.
    new_password: str = Field(min_length=8, max_length=200)


class LoginResponse(BaseModel):
    user_id: int
    email: EmailStr
    csrf_token: str


class MeResponse(BaseModel):
    authenticated: bool
    kind: str
    user_id: int | None = None
    email: str | None = None
    name: str | None = None
    role: str | None = None


class CsrfResponse(BaseModel):
    csrf_token: str
