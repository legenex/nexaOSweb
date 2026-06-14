"""Redaction guard: no secret bearing field may be serialised into the ledger or context.

A secret value belongs only in the Brain secret store. This guard is the structural backstop:
before any credential related payload, evidence, assessment, or context fragment is persisted or
returned, it is walked for a field whose name marks it as carrying a raw secret. A reference into
the secret store (credentials_ref, or a secret:// pointer) is explicitly allowed; a bare value
under a secret bearing name is not.

The guard is deny by default on field names, not on value heuristics, so it cannot be fooled by a
secret that happens not to look like one. Code paths that touch credentials call assert_no_secret
on what they are about to write, and the test suite proves a provided secret never reaches a step,
a run, or inject_context output.
"""

from typing import Any

# Field names that may only ever hold a reference, never a raw secret value. Compared against the
# lowercased key. Reference fields below are exempt.
SECRET_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "secret",
        "raw_secret",
        "secret_value",
        "value",
        "credential",
        "credentials",
        "credential_value",
        "api_key",
        "apikey",
        "api_secret",
        "password",
        "passwd",
        "token",
        "access_token",
        "refresh_token",
        "client_secret",
        "private_key",
    }
)

# Reference fields are the sanctioned way to point at a stored secret. They never hold the value.
ALLOWED_REFERENCE_FIELDS: frozenset[str] = frozenset({"credentials_ref", "secret_ref", "ref"})


class SecretLeakError(Exception):
    """Raised when a secret bearing field would be serialised into the ledger or context."""


def find_secret_fields(obj: Any, path: str = "") -> list[str]:
    """Return the paths of every secret bearing field that carries a non empty string value.

    Walks dicts and lists. A key in SECRET_FIELD_NAMES whose value is a non empty string is a
    leak, unless the key is an allowed reference field. A secret value is always a string, so a
    boolean control flag that happens to share a name (such as the risk credential tag) is not a
    leak; only a string under a secret bearing name is.
    """
    leaks: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else str(key)
            lowered = str(key).lower()
            if lowered in SECRET_FIELD_NAMES and lowered not in ALLOWED_REFERENCE_FIELDS:
                if isinstance(value, str) and value.strip():
                    leaks.append(here)
            leaks.extend(find_secret_fields(value, here))
    elif isinstance(obj, (list, tuple)):
        for index, item in enumerate(obj):
            leaks.extend(find_secret_fields(item, f"{path}[{index}]"))
    return leaks


def assert_no_secret(obj: Any, where: str = "payload") -> None:
    """Raise SecretLeakError if obj carries any secret bearing field. The seam guard."""
    leaks = find_secret_fields(obj)
    if leaks:
        raise SecretLeakError(
            f"refusing to serialise secret bearing field(s) into {where}: {', '.join(leaks)}"
        )
