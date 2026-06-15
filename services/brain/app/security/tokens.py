"""Single use token helpers for the password reset flow.

The raw token is what travels in the emailed link. Only its SHA-256 hash is persisted, so a leak of
the database cannot be replayed: an attacker would hold hashes, not usable links. Lookups hash the
supplied token and match on the stored hash.
"""

import hashlib
import secrets


def make_reset_token() -> tuple[str, str]:
    """Return (raw_token, token_hash). The raw token goes in the email, the hash is stored."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_reset_token(raw)


def hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
