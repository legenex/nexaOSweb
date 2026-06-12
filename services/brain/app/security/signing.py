"""HMAC signed tokens for the session cookie.

A token is base64url(payload).base64url(signature). The signature is HMAC SHA256 over
the payload using NEXA_SESSION_SECRET. This avoids a server side session store while
keeping the cookie tamper evident.
"""

import base64
import hashlib
import hmac
import time

from app.settings import get_settings

# Session lifetime in seconds (14 days)
SESSION_MAX_AGE = 14 * 24 * 60 * 60


def _key() -> bytes:
    return get_settings().nexa_session_secret.encode("utf-8")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def sign(payload: str) -> str:
    msg = payload.encode("utf-8")
    sig = hmac.new(_key(), msg, hashlib.sha256).digest()
    return f"{_b64encode(msg)}.{_b64encode(sig)}"


def unsign(token: str) -> str | None:
    try:
        msg_part, sig_part = token.split(".", 1)
        msg = _b64decode(msg_part)
        sig = _b64decode(sig_part)
    except (ValueError, Exception):
        return None
    expected = hmac.new(_key(), msg, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    return msg.decode("utf-8")


def make_session_token(user_id: int) -> str:
    return sign(f"{user_id}:{int(time.time())}")


def read_session_token(token: str) -> int | None:
    payload = unsign(token)
    if not payload:
        return None
    try:
        user_id_str, issued_str = payload.split(":", 1)
        user_id = int(user_id_str)
        issued = int(issued_str)
    except ValueError:
        return None
    if int(time.time()) - issued > SESSION_MAX_AGE:
        return None
    return user_id
