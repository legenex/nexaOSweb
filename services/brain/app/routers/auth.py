"""Auth routes for both the web companion and the desktop client."""

from datetime import UTC, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.email import send_email
from app.models.base import utcnow
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.schemas.auth import (
    CsrfResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
)
from app.schemas.users import ProfileUpdate
from app.security.auth import (
    Principal,
    clear_session,
    current_user,
    get_principal,
    issue_csrf,
    issue_session,
)
from app.security.passwords import hash_password, verify_password
from app.security.ratelimit import login_limiter, password_reset_limiter
from app.security.tokens import hash_reset_token, make_reset_token
from app.settings import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _app_base_url() -> str:
    """The public base URL used to build a reset link.

    Prefer the explicit NEXA_APP_BASE_URL, then the first configured CORS origin (the web
    companion's own origin in every real deployment), then a localhost dev fallback.
    """
    settings = get_settings()
    if settings.nexa_app_base_url:
        return settings.nexa_app_base_url.rstrip("/")
    origins = settings.cors_origin_list
    if origins:
        return origins[0].rstrip("/")
    return "http://localhost:5173"


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    if not login_limiter.allow(_client_key(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many login attempts")

    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        # Same message for unknown user and wrong password to avoid enumeration.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    csrf = issue_session(response, user.id, request)
    return LoginResponse(user_id=user.id, email=user.email, csrf_token=csrf)


@router.post("/password-reset/request", status_code=status.HTTP_204_NO_CONTENT)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> Response:
    """Start a reset: email a single use link to a known active account.

    Always returns 204 regardless of whether the email matches an account, so the endpoint cannot be
    used to enumerate users. When the email does match, a token row is stored (only its hash) and a
    link is sent. With SMTP unconfigured the mailer logs the link instead, so dev still works.
    """
    if not password_reset_limiter.allow(f"pwreset:{_client_key(request)}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many reset requests")

    user = db.query(User).filter(User.email == payload.email).first()
    if user is not None and user.status == "active":
        settings = get_settings()
        raw, token_hash = make_reset_token()
        expires_at = utcnow() + timedelta(minutes=settings.nexa_password_reset_ttl_minutes)
        db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
        db.commit()

        link = f"{_app_base_url()}/#reset?token={raw}"
        minutes = settings.nexa_password_reset_ttl_minutes
        body = (
            "We received a request to reset your nexaOSweb password.\n\n"
            f"Open this link to choose a new password (valid for {minutes} minutes):\n"
            f"{link}\n\n"
            "If you did not request this, you can safely ignore this email. Your password will "
            "not change until you open the link and set a new one.\n"
        )
        send_email(user.email, "Reset your nexaOSweb password", body)

    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(
    payload: PasswordResetConfirm,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> Response:
    """Finish a reset: spend the token and set the new password.

    The token is matched by hash. A missing, already used, or expired token returns the same 400 so
    a caller cannot tell which. On success the password is updated, an invited account is flipped to
    active, and the token is marked used so the link cannot be replayed.
    """
    if not password_reset_limiter.allow(f"pwreset:{_client_key(request)}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many reset attempts")

    token_hash = hash_reset_token(payload.token)
    row = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )
    # SQLite (dev) returns naive datetimes while Postgres (prod) returns aware ones. Normalize the
    # stored expiry to aware UTC so the comparison works the same on both backends.
    expires_at = row.expires_at if row is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if row is None or row.used_at is not None or expires_at < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired reset token")

    user = db.get(User, row.user_id)
    if user is None or user.status == "removed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired reset token")

    user.password_hash = hash_password(payload.new_password)
    if user.status == "invited":
        user.status = "active"
    row.used_at = utcnow()
    db.commit()

    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    # Clearing cookies is safe and idempotent, so it does not require auth or CSRF.
    clear_session(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeResponse)
def me(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> MeResponse:
    if principal.kind == "bearer":
        return MeResponse(authenticated=True, kind="bearer")
    user = db.get(User, principal.user_id) if principal.user_id else None
    return MeResponse(
        authenticated=True,
        kind="session",
        user_id=user.id if user else None,
        email=user.email if user else None,
        name=user.name if user else None,
        role=user.role if user else None,
    )


@router.patch("/me", response_model=MeResponse)
def update_me(
    payload: ProfileUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    # Self profile edit from Settings, General. Only the display name is editable here.
    if payload.name is not None:
        user.name = payload.name
    db.commit()
    db.refresh(user)
    return MeResponse(
        authenticated=True,
        kind="session",
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
    )


@router.get("/csrf", response_model=CsrfResponse)
def csrf(request: Request, response: Response) -> CsrfResponse:
    return CsrfResponse(csrf_token=issue_csrf(response, request))
