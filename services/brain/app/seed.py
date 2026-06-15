"""Durable owner and admin boot seed.

Reconciles the owner and admin accounts on startup so login survives a database move or a fresh
canonical database. Idempotent: it creates a missing account, always reconciles the role, and,
when NEXA_SEED_FORCE_PASSWORD is set, resets the password to the configured value so a recovery
run has a known good login. Emails and passwords come from the environment only, never from
committed code. The owner is the highest privilege account; the admin matches it except the admin
can never delete the owner (enforced in app.services.users).
"""

import logging

from sqlalchemy.orm import Session

from app.models.user import User
from app.security.passwords import hash_password
from app.settings import get_settings

logger = logging.getLogger("nexaos.seed")


def _ensure_account(
    db: Session,
    *,
    email: str,
    password: str,
    role: str,
    force_password: bool,
) -> None:
    email = (email or "").strip().lower()
    if not email:
        return
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        if not password:
            logger.warning("seed: no password configured for %s, cannot create", email)
            return
        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                role=role,
                status="active",
            )
        )
        logger.info("seed: created %s with role %s", email, role)
        db.commit()
        return
    changed = False
    if user.role != role:
        user.role = role
        changed = True
        logger.info("seed: reconciled %s to role %s", email, role)
    if user.status == "removed":
        user.status = "active"
        changed = True
    if force_password and password:
        user.password_hash = hash_password(password)
        changed = True
        logger.info("seed: reset password for %s", email)
    if changed:
        db.commit()


def seed_accounts(db: Session) -> None:
    """Ensure the owner and admin rows exist with the configured roles, idempotently."""
    settings = get_settings()
    force = settings.nexa_seed_force_password
    _ensure_account(
        db,
        email=settings.nexa_owner_email,
        password=settings.nexa_owner_password,
        role="owner",
        force_password=force,
    )
    _ensure_account(
        db,
        email=settings.nexa_admin_email,
        password=settings.nexa_admin_password,
        role="admin",
        force_password=force,
    )
