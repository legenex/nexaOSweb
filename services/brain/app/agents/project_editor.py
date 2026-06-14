"""Gated AI editor for the Projects workspace and the executor worktree.

The editor proposes a change to a single file, returns a diff summary, and writes nothing until
an explicit approval (or the executor's apply step) arrives. Apply re-checks the path safety gate,
writes the file, and records an applied build log entry that backs a later rollback.

Every read and write is confined to a root by ensure_within_root. The root defaults to the
project's own folder under NEXA_PROJECTS_ROOT, and the executor passes its isolated worktree root
instead, so the same gated propose and apply serve both the live workspace and an executor run
without either being able to escape its root.
"""

import difflib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.json_extract import synthesize_json
from app.models.project import BuildLogEntry, Project
from app.safety import ensure_within_root, safe_write_text
from app.settings import get_settings

logger = logging.getLogger(__name__)

_DIFF_CAP = 8000

_EDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "new_content": {"type": "string"},
        "change_summary": {"type": "string"},
    },
    "required": ["new_content", "change_summary"],
}


class EditorError(Exception):
    """Raised when a proposal cannot be made, applied, or rolled back."""


@dataclass
class RenderedEdit:
    """A proposed change before anything is persisted or written.

    before is the full prior content, or None when the file does not exist yet. after is the full
    intended content. The executor hashes intent plus after into a content idempotency key and
    compares after against the target before writing, so neither needs a database row to exist.
    """

    file_path: str
    before: str | None
    after: str
    summary: str
    diff_summary: str


def _project_dir(project: Project) -> Path:
    """Resolve and gate the project's own folder under the projects root."""
    settings = get_settings()
    return ensure_within_root(settings.nexa_projects_root, project.slug)


def _edit_root(project: Project, root: str | Path | None) -> Path:
    """The root every read and write of this edit is confined to.

    Defaults to the project folder; the executor passes its worktree so the same gate serves an
    isolated run. A root that is already gated (the worktree path) is re-resolved here, so a
    crafted file path still cannot escape it.
    """
    return Path(root) if root is not None else _project_dir(project)


def _diff_summary(before: str, after: str, file_path: str) -> str:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    diff = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
    )
    additions = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
    header = f"{additions} addition(s), {deletions} deletion(s) in {file_path}"
    body = "\n".join(diff)
    if len(body) > _DIFF_CAP:
        body = body[:_DIFF_CAP] + "\n... (diff truncated)"
    return f"{header}\n\n{body}".rstrip()


def _edit_prompt(file_path: str, before: str | None, instruction: str) -> str:
    current = before if before is not None else "(this file does not exist yet)"
    return (
        "You are editing a single project file. Apply the instruction and return the full "
        "new file content, not a patch. Keep the change minimal and faithful to the "
        "instruction. US market only.\n\n"
        f"File path: {file_path}\n"
        f"Instruction: {instruction}\n\n"
        "Current content:\n"
        f"{current}\n"
    )


def render_edit(
    project: Project,
    *,
    file_path: str,
    instruction: str,
    synthesize: Callable[..., dict[str, Any]] | None = None,
    root: str | Path | None = None,
) -> RenderedEdit:
    """Produce the intended change without persisting or writing anything.

    The path safety gate runs first, rooted at root (the project folder by default, the worktree
    for an executor run), so an escaping path is rejected before any model call. Returns the
    before and after content the caller can persist, hash for idempotency, or compare to disk.
    """
    synthesize = synthesize or synthesize_json
    base = _edit_root(project, root)
    target = ensure_within_root(base, file_path)  # raises PathSafetyError on escape
    before: str | None = target.read_text(encoding="utf-8") if target.exists() else None

    result = synthesize("agentic_code", _edit_prompt(file_path, before, instruction), _EDIT_SCHEMA)
    if not isinstance(result, dict) or "new_content" not in result:
        raise EditorError("the editor did not return new content")
    after = str(result.get("new_content", ""))
    summary = str(result.get("change_summary", "")).strip() or f"Edit {file_path}"
    return RenderedEdit(
        file_path=file_path,
        before=before,
        after=after,
        summary=summary,
        diff_summary=_diff_summary(before or "", after, file_path),
    )


def proposed_entry(db: Session, project: Project, rendered: RenderedEdit) -> BuildLogEntry:
    """Persist a rendered change as a proposed build log entry. Writes nothing to disk."""
    entry = BuildLogEntry(
        project_id=project.id,
        action="edit",
        status="proposed",
        summary=rendered.summary[:400],
        file_path=rendered.file_path,
        diff_summary=rendered.diff_summary,
        before_content=rendered.before,
        after_content=rendered.after,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def propose_edit(
    db: Session,
    project: Project,
    *,
    file_path: str,
    instruction: str,
    synthesize: Callable[..., dict[str, Any]] | None = None,
    root: str | Path | None = None,
) -> BuildLogEntry:
    """Generate a proposed change and persist it as a proposed build log entry.

    Nothing is written to disk. The path safety gate runs in render_edit, rooted at root, so an
    escaping path is rejected before any model call.
    """
    rendered = render_edit(
        project, file_path=file_path, instruction=instruction, synthesize=synthesize, root=root
    )
    return proposed_entry(db, project, rendered)


def apply_edit(
    db: Session,
    project: Project,
    entry: BuildLogEntry,
    *,
    root: str | Path | None = None,
) -> str:
    """Apply an approved proposal. Re-checks the path safety gate before writing.

    The write is confined to root: the project folder by default, the worktree for an executor
    run. safe_write_text re-resolves the path against that root and creates parents.
    """
    if entry.project_id != project.id:
        raise EditorError("proposal does not belong to this project")
    if entry.action != "edit" or entry.status != "proposed":
        raise EditorError("only a pending edit proposal can be applied")

    base = _edit_root(project, root)
    written = safe_write_text(base, entry.file_path, entry.after_content or "")
    entry.status = "applied"
    db.commit()
    db.refresh(entry)
    return str(written)


def rollback_edit(db: Session, project: Project, entry: BuildLogEntry) -> BuildLogEntry:
    """Undo an applied edit, restoring the prior content or removing a created file.

    Records a new applied rollback entry and marks the original rolled_back.
    """
    if entry.project_id != project.id:
        raise EditorError("build log entry does not belong to this project")
    if entry.action != "edit" or entry.status != "applied":
        raise EditorError("only an applied edit can be rolled back")

    project_dir = _project_dir(project)
    target = ensure_within_root(project_dir, entry.file_path)
    if entry.before_content is None:
        # The edit created the file; rolling back removes it.
        if target.exists():
            target.unlink()
        restored_note = "removed file created by the edit"
    else:
        safe_write_text(project_dir, entry.file_path, entry.before_content)
        restored_note = "restored prior content"

    entry.status = "rolled_back"
    rollback_entry = BuildLogEntry(
        project_id=project.id,
        action="rollback",
        status="applied",
        summary=f"Rolled back edit #{entry.id}: {restored_note}",
        file_path=entry.file_path,
        diff_summary=f"Reverted edit #{entry.id} on {entry.file_path}",
        before_content=entry.after_content,
        after_content=entry.before_content,
    )
    db.add(rollback_entry)
    db.commit()
    db.refresh(rollback_entry)
    return rollback_entry
