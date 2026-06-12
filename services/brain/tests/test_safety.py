"""Path safety gate and dangerous command guard."""

import pytest

from app.safety import (
    PROTECTED_BRANCHES,
    PathSafetyError,
    ensure_within_root,
    is_dangerous,
    safe_write_text,
)


def test_ensure_within_root_allows_child(tmp_path):
    target = ensure_within_root(tmp_path, "projects/alpha/plan.md")
    assert str(target).startswith(str(tmp_path.resolve()))


def test_ensure_within_root_blocks_escape(tmp_path):
    with pytest.raises(PathSafetyError):
        ensure_within_root(tmp_path, "../../etc/passwd")


def test_ensure_within_root_blocks_absolute_escape(tmp_path):
    with pytest.raises(PathSafetyError):
        ensure_within_root(tmp_path, "/etc/passwd")


def test_safe_write_text_creates_file(tmp_path):
    written = safe_write_text(tmp_path, "a/b/c.md", "hello")
    assert written.read_text() == "hello"


def test_is_dangerous_flags_destructive_commands():
    assert is_dangerous("rm -rf /")
    assert is_dangerous("git push --force origin main")
    assert not is_dangerous("git status")


def test_protected_branches_present():
    assert "main" in PROTECTED_BRANCHES
