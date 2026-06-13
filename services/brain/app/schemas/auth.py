"""Auth schemas."""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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
