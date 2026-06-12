"""Auth routes for both the web companion and the desktop client."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.schemas.auth import CsrfResponse, LoginRequest, LoginResponse, MeResponse
from app.security.auth import Principal, clear_session, get_principal, issue_csrf, issue_session
from app.security.passwords import verify_password
from app.security.ratelimit import login_limiter

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


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

    csrf = issue_session(response, user.id)
    return LoginResponse(user_id=user.id, email=user.email, csrf_token=csrf)


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
    )


@router.get("/csrf", response_model=CsrfResponse)
def csrf(response: Response) -> CsrfResponse:
    return CsrfResponse(csrf_token=issue_csrf(response))
