"""Safe zip extraction in capture."""

import io
import zipfile

import pytest

from app.zipcapture import ZipCaptureError, extract_zip


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_extracts_text_and_lists_assets(tmp_path):
    data = _zip(
        {
            "instructions.md": b"# Build a quiz funnel\n\nLead capture first.",
            "readme.txt": b"notes here",
            "logo.png": b"\x89PNG\r\n\x1a\n binary",
        }
    )
    folded, attachments = extract_zip(str(tmp_path), 42, data)
    assert "Build a quiz funnel" in folded
    assert "notes here" in folded
    # The image is a non text asset.
    kinds = {a["kind"] for a in attachments}
    assert "png" in kinds
    # Files landed under the item's extracted dir inside the uploads root.
    assert (tmp_path / "inbox" / "42" / "extracted" / "logo.png").exists()


def test_rejects_zip_slip_parent_traversal(tmp_path):
    data = _zip({"../../evil.txt": b"pwned"})
    with pytest.raises(ZipCaptureError):
        extract_zip(str(tmp_path), 1, data)
    # Nothing was written outside the root.
    assert not (tmp_path.parent / "evil.txt").exists()


def test_rejects_absolute_entry_path(tmp_path):
    data = _zip({"/etc/evil": b"pwned"})
    with pytest.raises(ZipCaptureError):
        extract_zip(str(tmp_path), 1, data)


def test_rejects_non_zip(tmp_path):
    with pytest.raises(ZipCaptureError):
        extract_zip(str(tmp_path), 1, b"this is not a zip")
