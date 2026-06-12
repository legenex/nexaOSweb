"""Password hashing with bcrypt. Hashes are stored, raw passwords never leave here.

bcrypt operates on at most 72 bytes, so the input is truncated to that boundary before
hashing and verifying to keep the two paths consistent.
"""

import bcrypt

_MAX_BYTES = 72


def _encode(raw: str) -> bytes:
    return raw.encode("utf-8")[:_MAX_BYTES]


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(_encode(raw), bcrypt.gensalt()).decode("ascii")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_encode(raw), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False
