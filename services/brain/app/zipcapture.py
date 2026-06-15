"""Safe zip extraction for capture intake.

A captured .zip is unpacked under the uploads root, never trusting the entry paths. A zip
slip attempt (an absolute path or a parent traversal in an entry name) is rejected outright.
Text content (instructions, readme, .md and similar) is folded into the captured item body so
the classifier sees it. Non text assets are listed as attachments.
"""

import io
import zipfile
from pathlib import Path

from app.safety import PathSafetyError, ensure_within_root
from app.util import safe_filename

# Extensions and names whose content is folded into the item body as text.
_TEXT_EXT = {".md", ".markdown", ".txt", ".rst", ".csv", ".json", ".yaml", ".yml"}
_TEXT_STEMS = {"readme", "instructions", "instruction", "notes", "brief", "spec"}

# Caps so a crafted archive cannot blow up the body or the disk.
_MAX_FOLDED_CHARS = 16000
_MAX_ENTRY_BYTES = 5 * 1024 * 1024


class ZipCaptureError(Exception):
    """Raised when an archive is unsafe or cannot be read."""


def _is_unsafe_entry(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/"):
        return True
    parts = normalized.split("/")
    return ".." in parts or any(part == "" and idx == 0 for idx, part in enumerate(parts))


def _safe_relative(item_id: int, name: str) -> Path:
    base = Path("inbox") / str(item_id) / "extracted"
    components = [safe_filename(part) for part in name.replace("\\", "/").split("/") if part]
    return base.joinpath(*components) if components else base / "entry"


def extract_zip(uploads_root: str, item_id: int, data: bytes) -> tuple[str, list[dict]]:
    """Extract an archive safely. Returns (folded_text, attachments).

    Raises ZipCaptureError if the archive is not a zip or contains an unsafe entry path.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ZipCaptureError("not a valid zip archive") from exc

    folded: list[str] = []
    attachments: list[dict] = []
    folded_len = 0

    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            raw = info.filename
            # Reject zip slip before touching the filesystem.
            if _is_unsafe_entry(raw):
                raise ZipCaptureError(f"unsafe zip entry path: {raw}")
            if info.file_size > _MAX_ENTRY_BYTES:
                attachments.append({"file": raw, "kind": "skipped-too-large"})
                continue

            relative = _safe_relative(item_id, raw)
            # Defense in depth: the resolved path must still be inside the uploads root.
            try:
                target = ensure_within_root(uploads_root, relative)
            except PathSafetyError as exc:
                raise ZipCaptureError(f"unsafe zip entry path: {raw}") from exc

            content = archive.read(info)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

            suffix = Path(raw).suffix.lower()
            stem = Path(raw).stem.lower()
            rel = str(relative)
            if (suffix in _TEXT_EXT or stem in _TEXT_STEMS) and folded_len < _MAX_FOLDED_CHARS:
                text = content.decode("utf-8", errors="replace")
                snippet = text[: _MAX_FOLDED_CHARS - folded_len]
                folded.append(f"## {Path(raw).name}\n\n{snippet}")
                folded_len += len(snippet)
            else:
                attachments.append({"file": rel, "kind": suffix.lstrip(".") or "file"})

    return ("\n\n".join(folded), attachments)
