"""User management: list, create, invite, change role, and remove.

Operates over the users table. Create directly provisions an active user with a password,
so an owner can add people without an email invite round trip. Invite creates a user in the
invited status with an unusable password placeholder (no login until a password is set, either
by a later email flow or by an owner updating the account). Remove is a soft delete that flips
status to removed and hides the row, so foreign keys from items and projects stay intact, in
line with the additive only data rule.

Managing users (create, invite, change role, set a password, remove) is limited to owner and
admin accounts. Members can read the list but cannot mutate it.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.schemas.users import UserCreate, UserInvite, UserRead, UserUpdate
from app.security.auth import Principal, current_user, get_principal
from app.security.passwords import hash_password

router = APIRouter(prefix="/users", tags=["users"])

MANAGER_ROLES = {"owner", "admin"}


def require_manager(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> User:
    """Only owners and admins may manage other users.

    The desktop bearer is a trusted machine to machine client, so it passes through and acts as
    the earliest user (the owner) just like elsewhere. A web session must belong to an owner or
    admin; members can read the user list but not mutate it.
    """
    if principal.kind == "bearer":
        actor = db.query(User).order_by(User.id.asc()).first()
        if actor is None:
            raise HTTPException(http_status.HTTP_401_UNAUTHORIZED, "no user provisioned")
        return actor
    actor = db.get(User, principal.user_id) if principal.user_id else None
    if actor is None:
        raise HTTPException(http_status.HTTP_401_UNAUTHORIZED, "unknown user")
    if actor.role not in MANAGER_ROLES:
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN, "only an owner or admin can manage users"
        )
    return actor


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


@router.post("", response_model=UserRead, status_code=http_status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    _actor: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> User:
    """Directly create an active user with a password set, ready to sign in.

    If a soft removed user already holds the email, reactivate that row in place rather than
    colliding on the unique email index, keeping their items and projects attached.
    """
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None and existing.status != "removed":
        raise HTTPException(http_status.HTTP_409_CONFLICT, "a user with that email exists")
    if existing is not None:
        existing.password_hash = hash_password(payload.password)
        existing.name = payload.name
        existing.role = payload.role
        existing.status = "active"
        db.commit()
        db.refresh(existing)
        return existing
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        role=payload.role,
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/invite", response_model=UserRead, status_code=http_status.HTTP_201_CREATED)
def invite_user(
    payload: UserInvite,
    _actor: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> User:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(http_status.HTTP_409_CONFLICT, "a user with that email exists")
    # An unusable random placeholder hash: the invited user cannot log in until a password
    # is set, either by a later email flow or by an owner updating the account.
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
    actor: User = Depends(require_manager),
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
    # A password set is handled specially: hash it, never store the raw value, and make an
    # invited account usable by flipping it to active unless the caller set a status too.
    password = fields.pop("password", None)
    if password is not None:
        user.password_hash = hash_password(password)
        if user.status == "invited" and "status" not in fields:
            user.status = "active"
    for field, value in fields.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=UserRead)
def remove_user(
    user_id: int,
    actor: User = Depends(require_manager),
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
