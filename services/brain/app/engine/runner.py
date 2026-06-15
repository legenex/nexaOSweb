"""The sandboxed command runner: run a bounded command inside a workspace, nowhere else.

run_in_workspace executes a single command with the workspace directory as its working directory,
captures stdout, stderr, and the exit code, and enforces a hard wall before anything runs:

  - The workspace directory is re-validated under the builds root on every call, so a stored path is
    never trusted.
  - The dangerous command guard refuses destructive commands, which includes every git force push.
  - A push that targets a protected branch is refused even without a force flag.
  - A command that references a path outside the workspace (an absolute path elsewhere, or a parent
    traversal that escapes) is refused, so it cannot read or write outside its box.

A refused command raises CommandRefused and never reaches the shell. The command runs without a
shell: it is split into argv, so shell metacharacters and compound operators do not chain a second
command past the guard. The environment is scrubbed of secrets before the command runs, so a
provider key can never leak into an agent's command. A run that exceeds its timeout is killed and
returned as timed_out.
"""

import os
import shlex
import subprocess
from dataclasses import dataclass, field

from app.engine.workspace import Workspace, builds_root
from app.safety import (
    PROTECTED_BRANCHES,
    PathSafetyError,
    ensure_within_root,
    is_dangerous,
)

# How long a single command may run before it is killed and returned as a timeout.
DEFAULT_TIMEOUT_SECONDS = 300

# Environment variable names whose value must never reach a command. Anything matching these
# fragments is dropped from the scrubbed environment, so provider keys and the Brain's own secrets
# stay server side and never enter an agent's command.
_SECRET_NAME_FRAGMENTS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "BEARER")
_SECRET_NAME_PREFIXES = ("NEXA_",)


class CommandRefused(Exception):
    """Raised when the guard refuses a command before it runs. It never reaches the shell."""


@dataclass
class CommandResult:
    """The captured outcome of a command that was allowed to run.

    A refused command never produces a CommandResult: it raises CommandRefused instead.
    """

    command: str
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    argv: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def _as_argv(command: str | list[str]) -> list[str]:
    if isinstance(command, str):
        argv = shlex.split(command)
    else:
        argv = [str(part) for part in command]
    if not argv:
        raise CommandRefused("an empty command cannot run")
    return argv


def _is_protected_push(argv: list[str]) -> bool:
    """True when the command is a git push that targets a protected branch.

    A push is refused if any argument names a protected branch, whether as a bare ref or as the
    destination of a refspec (the part after the colon, or a bare ref pushed to its own name). Force
    pushes on any branch are already refused by the dangerous command guard.
    """
    lowered = [part.lower() for part in argv]
    if "git" not in lowered or "push" not in lowered:
        return False
    protected = set(PROTECTED_BRANCHES)
    for part in argv:
        if part.startswith("-"):
            continue
        # A refspec src:dst targets dst; a bare ref targets the same name on the remote.
        candidate = part.split(":")[-1] if ":" in part else part
        candidate = candidate.split("/")[-1]
        if candidate in protected:
            return True
    return False


def _escapes_workspace(argv: list[str], workspace_path) -> bool:
    """True when any argument names a filesystem path outside the workspace.

    Only path shaped arguments are checked: an absolute path, a home path, or one that contains a
    directory separator or a parent traversal. Each is resolved against the workspace and refused if
    it lands outside it. Non path arguments (flags, messages, remote names, urls) are ignored.
    """
    for part in argv:
        if not part or part.startswith("-"):
            continue
        looks_like_path = (
            part.startswith("/")
            or part.startswith("~")
            or part == ".."
            or "/" in part
        )
        if not looks_like_path:
            continue
        # A url such as https://host/repo.git contains a separator but is not a local path; its
        # scheme makes it resolve harmlessly under the workspace, so it is never falsely refused.
        candidate = os.path.expanduser(part)
        try:
            ensure_within_root(workspace_path, candidate)
        except PathSafetyError:
            return True
    return False


def _guard(argv: list[str], workspace_path) -> None:
    command_str = " ".join(argv)
    if is_dangerous(command_str):
        raise CommandRefused(f"refused dangerous command: {command_str}")
    if _is_protected_push(argv):
        raise CommandRefused(f"refused push to a protected branch: {command_str}")
    if _escapes_workspace(argv, workspace_path):
        raise CommandRefused(f"refused command that escapes the workspace: {command_str}")


def _scrubbed_env(extra: dict[str, str] | None) -> dict[str, str]:
    """The process environment with secret named variables removed, plus any explicit extras.

    Extras are applied after scrubbing, so a caller can pass a needed non secret value, but cannot
    smuggle a dropped secret back in under its original name.
    """
    env: dict[str, str] = {}
    for name, value in os.environ.items():
        upper = name.upper()
        if any(upper.startswith(prefix) for prefix in _SECRET_NAME_PREFIXES):
            continue
        if any(fragment in upper for fragment in _SECRET_NAME_FRAGMENTS):
            continue
        env[name] = value
    if extra:
        for name, value in extra.items():
            upper = name.upper()
            if any(upper.startswith(p) for p in _SECRET_NAME_PREFIXES) or any(
                fragment in upper for fragment in _SECRET_NAME_FRAGMENTS
            ):
                continue
            env[name] = str(value)
    return env


def run_in_workspace(
    workspace: Workspace,
    command: str | list[str],
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Run one command inside the workspace, bounded and guarded, and capture its result.

    The workspace directory is re-validated under the builds root, then the command is guarded
    (dangerous commands, protected branch pushes, and path escapes are refused with CommandRefused).
    An allowed command runs with the workspace as its working directory, a scrubbed environment, and
    the given timeout. stdout, stderr, and the exit code are captured; a timeout is killed and
    returned with timed_out set and a null exit code.
    """
    # Never trust a stored path: the workspace must still resolve under the builds root.
    try:
        path = ensure_within_root(builds_root(), workspace.path)
    except PathSafetyError as exc:
        raise CommandRefused(f"workspace path is outside the builds root: {exc}") from exc
    if not path.is_dir():
        raise CommandRefused(f"workspace directory does not exist: {path}")

    argv = _as_argv(command)
    _guard(argv, path)

    try:
        result = subprocess.run(
            argv,
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_scrubbed_env(env),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(
            command=" ".join(argv),
            exit_code=None,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
            argv=argv,
        )

    return CommandResult(
        command=" ".join(argv),
        exit_code=result.returncode,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
        timed_out=False,
        argv=argv,
    )
