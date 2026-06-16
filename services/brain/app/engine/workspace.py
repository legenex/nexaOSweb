"""The project workspace sandbox: an isolated working directory per project under the runtime root.

A workspace is where the Agent Build Engine does its work, never the served project folder under
NEXA_PROJECTS_ROOT. Given a project, prepare_workspace resolves a directory under NEXA_RUNTIME_ROOT
through the path safety gate (so a crafted slug can never escape the runtime root), then clones the
target git repo into it or initialises a fresh one with a baseline commit to branch from. Nothing
outside that directory is ever touched.

There is one agent execution root. The engine sandbox and the executor's worktrees share the single
NEXA_RUNTIME_ROOT boundary (the former separate NEXA_BUILDS_ROOT is collapsed into it), so an
external coding agent run is confined by the same ensure_within_root gate the executor already
proved, and a build run can edit directly inside the executor's worktree.

The git work here is limited to opening the workspace: clone, init, and the baseline commit. It runs
no build commands and never pushes; arbitrary build commands go through app/engine/runner.py, which
carries the refusal rules. Both layers share the same dangerous command guard.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.models.project import Project
from app.safety import ensure_within_root, is_dangerous
from app.settings import get_settings

# Git identity for the baseline commit in a freshly initialised workspace, so a commit exists to
# branch from. It is local to the workspace and never touches the user's global git config.
_GIT_USER = ("-c", "user.email=engine@nexaos.local", "-c", "user.name=nexaOS build engine")


class WorkspaceError(Exception):
    """Raised when a workspace cannot be prepared or its git repo cannot be opened."""


@dataclass
class Workspace:
    """One prepared, isolated working directory for a project under the builds root.

    path is the validated absolute directory; every command and edit is confined to it. repo_url is
    the source that was cloned, or None when the workspace was initialised fresh.
    """

    project_id: int | None
    slug: str
    path: Path
    repo_url: str | None = None


def builds_root() -> Path:
    """The single agent execution root, resolved absolute. Every workspace and every executor
    worktree lives under this one directory. It is NEXA_RUNTIME_ROOT: the engine sandbox was
    collapsed onto the runtime root so the engine and the executor share one ensure_within_root
    boundary rather than two parallel sandbox systems."""
    return Path(get_settings().nexa_runtime_root).expanduser().resolve()


def _run_git(cwd: Path, *args: str) -> str:
    command = ["git", *args]
    if is_dangerous(" ".join(command)):
        raise WorkspaceError(f"refused dangerous command: {' '.join(command)}")
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise WorkspaceError(f"git {' '.join(args)} failed in {cwd}: {detail}")
    return result.stdout


def _has_commit(repo: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _init_fresh(path: Path) -> None:
    """Initialise a fresh git repo with a baseline commit, so there is a HEAD to branch from."""
    path.mkdir(parents=True, exist_ok=True)
    _run_git(path, "init")
    if not _has_commit(path):
        _run_git(path, *_GIT_USER, "add", "-A")
        _run_git(path, *_GIT_USER, "commit", "-m", "engine: baseline workspace", "--allow-empty")


def _clone(repo_url: str, path: Path) -> None:
    """Clone the target repo into the workspace directory under the builds root.

    The clone runs from the builds root with the workspace directory as the explicit target, so the
    repo can never land outside the sandbox. repo_url is checked by the dangerous command guard.
    """
    if is_dangerous(repo_url):
        raise WorkspaceError(f"refused dangerous repo url: {repo_url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    command = ["git", "clone", repo_url, str(path)]
    result = subprocess.run(
        command, cwd=str(path.parent), capture_output=True, text=True
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise WorkspaceError(f"git clone failed for {repo_url}: {detail}")


def prepare_workspace(
    project: Project,
    *,
    repo_url: str | None = None,
    subdir: str | None = None,
) -> Workspace:
    """Prepare an isolated working directory for a project under the builds root.

    The directory is project.slug (or an explicit subdir) resolved through ensure_within_root so it
    can never escape NEXA_RUNTIME_ROOT. Preparation is idempotent: an existing git checkout is reused
    as is. Otherwise, with a repo_url the target repo is cloned into the directory, and without one a
    fresh repo is initialised with a baseline commit. No file outside the directory is touched.
    """
    if project is None:
        raise WorkspaceError("a workspace requires a project")
    slug = (subdir or project.slug or "").strip()
    if not slug:
        raise WorkspaceError("a workspace requires a project slug")

    root = builds_root()
    root.mkdir(parents=True, exist_ok=True)
    # The single line that guarantees no escape: a crafted slug resolving outside the builds root
    # raises here before any directory is created or any git command runs.
    path = ensure_within_root(root, slug)

    if (path / ".git").exists():
        # Idempotent reuse: the workspace is already a checkout, leave it untouched.
        return Workspace(
            project_id=project.id, slug=slug, path=path, repo_url=repo_url
        )

    if path.exists() and any(path.iterdir()):
        raise WorkspaceError(
            f"workspace path is not empty and is not a git checkout: {path}"
        )

    if repo_url:
        _clone(repo_url, path)
    else:
        _init_fresh(path)

    return Workspace(project_id=project.id, slug=slug, path=path, repo_url=repo_url)
