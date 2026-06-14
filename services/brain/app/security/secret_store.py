"""The Brain secret store.

Provider secrets live only here, on the server, under NEXA_SECRETS_ROOT. The runtime ledger,
the readiness assessment, agent context, and every API response carry a reference into this store
(secret://<provider>), never the value. The store is write and reference only from the API's point
of view: no HTTP route ever returns a stored secret. The only sanctioned read is read_secret, used
server side by the model router to hand a connected provider key to litellm at call time; the value
is read on the server and never crosses the API boundary.

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


def mask_hint(secret: str) -> str:
    """A non secret last four hint for a stored key, for example ****1234.

    The hint reveals only the trailing characters so an operator can recognise which key is
    connected without the value ever being exposed. It is safe to persist and return; it is not a
    secret bearing field.
    """
    tail = secret.strip()[-4:]
    return f"****{tail}" if tail else "****"


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


def read_secret(provider: str) -> str | None:
    """Read a stored provider secret, or None when none is stored. Server side only.

    This is the single sanctioned read of the store, used by the model router to resolve a
    connected provider key and hand it to litellm per call. There is deliberately no HTTP route
    that calls this: the value is read on the server and never crosses the API boundary, is never
    logged, and never enters the ledger. The redaction guard is the structural backstop on every
    serialised seam.
    """
    path = _path_for(provider)
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def delete_secret(provider: str) -> None:
    """Remove a stored provider secret if present. Used when a provider is disconnected."""
    path = _path_for(provider)
    if path.exists():
        path.unlink()
