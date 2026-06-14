"""Provision or update a user. Run after alembic upgrade head.

Usage:
    python -m scripts.create_user someone@example.com a-strong-password
    python -m scripts.create_user nick@legenex.com 'MoreLeads@2026' --role owner
    python -m scripts.create_user team@legenex.com 'nexaos123' --role admin --name Team

Creating or updating always sets the account active (ready to sign in) unless --status is
given, and resets the password to the supplied value. Use this to recover a locked out owner
or to turn an invited row into a working login.
"""

import argparse

from app.db import SessionLocal
from app.models.user import User
from app.security.passwords import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a nexaOSweb user.")
    parser.add_argument("email")
    parser.add_argument("password")
    parser.add_argument(
        "--role",
        choices=["owner", "admin", "member"],
        default="member",
        help="account role (default member).",
    )
    parser.add_argument(
        "--status",
        choices=["active", "invited", "removed"],
        default="active",
        help="account status (default active, ready to sign in).",
    )
    parser.add_argument("--name", default=None, help="optional display name.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email).first()
        if existing is not None:
            existing.password_hash = hash_password(args.password)
            existing.role = args.role
            existing.status = args.status
            if args.name is not None:
                existing.name = args.name
            print(f"updated {args.email} (role={args.role}, status={args.status})")
        else:
            db.add(
                User(
                    email=args.email,
                    password_hash=hash_password(args.password),
                    role=args.role,
                    status=args.status,
                    name=args.name,
                )
            )
            print(f"created {args.email} (role={args.role}, status={args.status})")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
