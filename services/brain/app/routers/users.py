"""User management: list, invite, change role, and remove.

Operates over the users table. Invite creates a user in the invited status with an unusable
password placeholder (no login until a real password flow sets one). Remove is a soft delete
that flips status to removed and hides the row, so foreign keys from items and projects stay
intact, in line with the additive only data rule.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.schemas.users import UserInvite, UserRead, UserUpdate
from app.security.auth import current_user
from app.security.passwords import hash_password

router = APIRouter(prefix="/users", tags=["users"])


def _load(user_id: int, db: Session) -> User:
    user = db.get(User, user_id)
    if user is None or user.status == "removed":
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "user not found")
    return user


@router.get("", response_model=list[UserRead])
def list_users(
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[User]:
    return (
        db.query(User)
        .filter(User.status != "removed")
        .order_by(User.id.asc())
        .all()
    )


@router.post("/invite", response_model=UserRead, status_code=http_status.HTTP_201_CREATED)
def invite_user(
    payload: UserInvite,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> User:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(http_status.HTTP_409_CONFLICT, "a user with that email exists")
    # An unusable random placeholder hash: the invited user cannot log in until a real
    # password flow (a later milestone) sets one.
    user = User(
        email=payload.email,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        name=payload.name,
        role=payload.role,
        status="invited",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    actor: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> User:
    user = _load(user_id, db)
    fields = payload.model_dump(exclude_none=True)
    # Guard against the owner locking themselves out of the owner role.
    demoting_self = (
        user.id == actor.id
        and user.role == "owner"
        and fields.get("role", "owner") != "owner"
    )
    if demoting_self:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT, "the owner cannot demote their own account"
        )
    for field, value in fields.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=UserRead)
def remove_user(
    user_id: int,
    actor: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> User:
    user = _load(user_id, db)
    if user.id == actor.id:
        raise HTTPException(http_status.HTTP_409_CONFLICT, "you cannot remove your own account")
    # Soft delete: keep the row so its items and projects keep their owner reference.
    user.status = "removed"
    db.commit()
    db.refresh(user)
    return user
