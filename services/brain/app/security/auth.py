"""Auth dependencies.

Two clients are supported:

- The desktop app sends a static bearer token equal to NEXA_DESKTOP_BEARER. Bearer
  requests are trusted machine to machine and skip CSRF.
- The web companion uses an httpOnly session cookie. Any state changing request
  (POST, PUT, PATCH, DELETE) must also carry a CSRF token that matches the CSRF cookie
  (double submit).
"""

import hmac
import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.security.signing import make_session_token, read_session_token
from app.settings import get_settings

SESSION_COOKIE = "nexa_session"
CSRF_COOKIE = "nexa_csrf"
CSRF_HEADER = "X-CSRF-Token"

STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class Principal:
    kind: str  # "session" or "bearer"
    user_id: int | None


def _cookie_secure(request: Request | None) -> bool:
    """Mark cookies Secure when production forces HTTPS or the live request is HTTPS.

    The NEXA_PUBLIC_HTTPS flag forces Secure for production, where TLS terminates at Nginx and
    the app may see a plain scheme. Falling back to the live request scheme means a plain HTTP
    localhost dev session gets non Secure cookies, so the browser actually stores them. Without
    this, a Secure cookie set over plain HTTP is silently dropped by the browser, the session
    never sticks, and sign in appears to do nothing.
    """
    if get_settings().nexa_public_https:
        return True
    return request is not None and request.url.scheme == "https"


def issue_session(response: Response, user_id: int, request: Request | None = None) -> str:
    """Set the session cookie and a fresh CSRF cookie. Returns the CSRF token."""
    token = make_session_token(user_id)
    secure = _cookie_secure(request)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    return issue_csrf(response, request)


def issue_csrf(response: Response, request: Request | None = None) -> str:
    """Set a readable CSRF cookie for the double submit pattern. Returns the token."""
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        httponly=False,
        samesite="lax",
        secure=_cookie_secure(request),
        path="/",
    )
    return csrf


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def get_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    settings = get_settings()

    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
        if settings.nexa_desktop_bearer and hmac.compare_digest(
            token, settings.nexa_desktop_bearer
        ):
            return Principal(kind="bearer", user_id=None)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid bearer token")

    cookie = request.cookies.get(SESSION_COOKIE)
    user_id = read_session_token(cookie) if cookie else None
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")

    if request.method in STATE_CHANGING:
        csrf_cookie = request.cookies.get(CSRF_COOKIE)
        csrf_header = request.headers.get(CSRF_HEADER)
        if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf validation failed")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")
    return Principal(kind="session", user_id=user.id)


def current_user(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> User:
    """Require a real user. Bearer (desktop) acts as the first user when present."""
    if principal.user_id is not None:
        user = db.get(User, principal.user_id)
        if user is not None:
            return user
    # Desktop bearer: act as the earliest user so single user setups work.
    user = db.query(User).order_by(User.id.asc()).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no user provisioned")
    return user
