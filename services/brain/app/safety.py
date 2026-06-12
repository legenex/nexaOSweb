"""Path safety gate and the dangerous command guard.

Every write to the on disk project and upload roots goes through ensure_within_root so a
crafted name cannot escape the configured root. is_dangerous and PROTECTED_BRANCHES back
the builder guard used by the Execute stage.
"""

import re
from pathlib import Path

# Branches that are never force pushed or rewritten.
PROTECTED_BRANCHES = ["main", "master", "production", "release"]

_DANGEROUS_PATTERNS = [
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r":\(\)\s*\{.*\};\s*:"),  # fork bomb
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if="),
    re.compile(r"\bgit\s+push\b.*--force"),
    re.compile(r"\bgit\s+push\b.*-f\b"),
    re.compile(r">\s*/dev/sd"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bchmod\s+-R\s+777\b"),
]


class PathSafetyError(Exception):
    """Raised when a candidate path would escape its root."""


def ensure_within_root(root: str | Path, candidate: str | Path) -> Path:
    """Resolve candidate against root and verify it stays inside the root.

    Returns the resolved absolute path. Raises PathSafetyError on escape.
    """
    root_path = Path(root).expanduser().resolve()
    candidate_path = Path(candidate)
    if candidate_path.is_absolute():
        target = candidate_path.resolve()
    else:
        target = (root_path / candidate_path).resolve()
    if target != root_path and root_path not in target.parents:
        raise PathSafetyError(f"path {target} escapes root {root_path}")
    return target


def safe_write_text(root: str | Path, relative: str | Path, content: str) -> Path:
    """Write text inside the root, creating parent directories first."""
    target = ensure_within_root(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def safe_write_bytes(root: str | Path, relative: str | Path, content: bytes) -> Path:
    target = ensure_within_root(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def is_dangerous(command: str) -> bool:
    text = command.lower()
    return any(pattern.search(text) for pattern in _DANGEROUS_PATTERNS)
