"""Small text helpers shared across the Brain."""

import re
import unicodedata
from pathlib import Path

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str, fallback: str = "item") -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", normalized.lower()).strip("-")
    return slug[:160] or fallback


def safe_filename(name: str | None, fallback: str = "upload.bin") -> str:
    """Reduce an uploaded name to a bare, safe basename."""
    if not name:
        return fallback
    base = Path(name).name  # drop any directory components
    base = base.replace("\x00", "")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned or fallback
