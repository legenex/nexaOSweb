"""The Brain secret store.

Provider secrets live only here, on the server, under NEXA_SECRETS_ROOT. The runtime ledger,
the readiness assessment, agent context, and every API response carry a reference into this store
(secret://<provider>), never the value. There is deliberately no function that returns a stored
secret to a caller: the store is write and reference only from the application's point of view.
The router that needs a provider key at call time reads it here on the server, never over HTTP.

Storing a secret as a file under a safe root mirrors how provider keys live in the server side
.env (per the secrets rule): the value never crosses the API boundary.
"""

from pathlib import Path

from app.safety import safe_write_text
from app.settings import get_settings

# The reference scheme written onto the Integration row and the runtime step. A pointer, never a
# value.
_REF_SCHEME = "secret://"


def _slug(provider: str) -> str:
    """A filesystem safe provider slug. The path safety gate is the final guard on escape."""
    safe = provider.strip().lower()
    cleaned = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in safe)
    return cleaned or "unknown"


def secret_ref(provider: str) -> str:
    """The stable reference for a provider's secret. Contains no secret material."""
    return f"{_REF_SCHEME}{_slug(provider)}"


def is_secret_ref(value: object) -> bool:
    return isinstance(value, str) and value.startswith(_REF_SCHEME)


def _path_for(provider: str) -> Path:
    settings = get_settings()
    return Path(settings.nexa_secrets_root).expanduser().resolve() / f"{_slug(provider)}.secret"


def store_secret(provider: str, secret: str) -> str:
    """Write a provider secret to the server side store and return its reference.

    The secret never leaves this function as a return value. The caller receives only the
    reference, which is what is recorded on the Integration row and the runtime step.
    """
    settings = get_settings()
    relative = f"{_slug(provider)}.secret"
    safe_write_text(settings.nexa_secrets_root, relative, secret)
    return secret_ref(provider)


def has_secret(provider: str) -> bool:
    """Whether a secret is stored for the provider. Never reveals the value."""
    return _path_for(provider).exists()
