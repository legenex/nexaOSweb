"""Provision or update a user. Run after alembic upgrade head.

Usage: python -m scripts.create_user someone@example.com a-strong-password
"""

import argparse

from app.db import SessionLocal
from app.models.user import User
from app.security.passwords import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a nexaOSweb user.")
    parser.add_argument("email")
    parser.add_argument("password")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email).first()
        if existing is not None:
            existing.password_hash = hash_password(args.password)
            print(f"updated password for {args.email}")
        else:
            db.add(User(email=args.email, password_hash=hash_password(args.password)))
            print(f"created user {args.email}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
