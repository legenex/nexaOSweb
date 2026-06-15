"""The Claude Code backend: the engine's default coding agent, run headless in a workspace.

This adapter drives the Claude Code CLI in headless print mode (claude -p ... --output-format json)
with the workspace as its working directory. It hands the task to the agent as the prompt, lets the
agent edit files inside the workspace, then captures the result: the proposed diff, the files
touched, the CLI transcript, a short reasoning summary, the exit status, and the cost or token
estimate the CLI reported.

Two boundaries this adapter holds:

  - Secrets stay server side. ANTHROPIC_API_KEY is read from settings and injected directly into the
    CLI process environment, never into the prompt and never into the returned result. Every other
    secret named variable is scrubbed from the CLI environment, so only the one key the CLI needs is
    present. The key value is redacted from the transcript, diff, and reasoning before they are
    returned, so a key can never leak out through the result either.
  - Writes stay inside the workspace. The workspace path is re validated under the builds root
    before the CLI runs, the CLI runs with that directory as its cwd, and the diff is captured
    through the guarded runner, which refuses any path that escapes the workspace.

The agent proposes; it never commits. The diff is captured but left uncommitted in the workspace for
the downstream gate to approve or reject.
"""

import os
import subprocess
from dataclasses import dataclass

from app.engine.backends.base import AgentBackend, AgentResult, BackendError, BackendHealth
from app.engine.runner import run_in_workspace
from app.engine.workspace import Workspace, builds_root
from app.safety import PathSafetyError, ensure_within_root
from app.settings import get_settings

# How long a headless agent run may take before it is killed. Agent runs are long compared to a
# single shell command, so this is generous; the orchestrator can pass a tighter bound per run.
DEFAULT_AGENT_TIMEOUT_SECONDS = 1800

# How long the cheap health and git capture commands may take.
_PROBE_TIMEOUT_SECONDS = 15
_GIT_TIMEOUT_SECONDS = 30

# The longest reasoning summary we keep. The CLI's final message can be long; the engine wants a
# short summary, so it is truncated rather than carried whole.
_REASONING_LIMIT = 2000

# Environment variable name fragments and prefixes whose values must never reach the CLI process,
# matching the runner's scrub. ANTHROPIC_API_KEY would match API_KEY here, so it is scrubbed with
# everything else and then re injected explicitly from settings, never inherited ambiently.
_SECRET_NAME_FRAGMENTS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "BEARER")
_SECRET_NAME_PREFIXES = ("NEXA_",)


@dataclass
class _CliOutput:
    """The fields parsed out of the CLI's json result. Missing fields stay None."""

    reasoning: str = ""
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


def _redact(text: str, secret: str) -> str:
    """Replace a secret value with a marker wherever it appears, so it cannot leak through the
    returned output."""
    if not text or not secret:
        return text or ""
    return text.replace(secret, "***")


def _cli_env(api_key: str) -> dict[str, str]:
    """The environment for the CLI: the process environment scrubbed of every secret, then the one
    Anthropic key injected from settings. PATH and HOME survive the scrub so the CLI is found and
    can read its own config; no other provider key or Brain secret is passed through."""
    env: dict[str, str] = {}
    for name, value in os.environ.items():
        upper = name.upper()
        if any(upper.startswith(prefix) for prefix in _SECRET_NAME_PREFIXES):
            continue
        if any(fragment in upper for fragment in _SECRET_NAME_FRAGMENTS):
            continue
        env[name] = value
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    return env


def _parse_porcelain(porcelain: str) -> list[str]:
    """Parse git status --porcelain into a list of workspace relative paths that changed."""
    files: list[str] = []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        # Each line is "XY path"; the path begins at column 3. A rename is "old -> new".
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"')
        if path:
            files.append(path)
    return files


def _parse_output(stdout: str) -> _CliOutput:
    """Parse the CLI's --output-format json into the reasoning summary and the cost estimate.

    The headless CLI prints one json object: result is the agent's final message, total_cost_usd and
    usage carry the estimate. Parsing is defensive: malformed or plain output falls back to a
    truncated stdout as the reasoning and leaves the estimate unset.
    """
    import json

    text = (stdout or "").strip()
    if not text:
        return _CliOutput()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return _CliOutput(reasoning=text[:_REASONING_LIMIT])
    if not isinstance(data, dict):
        return _CliOutput(reasoning=text[:_REASONING_LIMIT])

    reasoning = str(data.get("result") or "").strip()[:_REASONING_LIMIT]
    cost = data.get("total_cost_usd")
    cost_usd = float(cost) if isinstance(cost, (int, float)) else None
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    inp = usage.get("input_tokens")
    out = usage.get("output_tokens")
    return _CliOutput(
        reasoning=reasoning,
        cost_usd=cost_usd,
        input_tokens=int(inp) if isinstance(inp, int) else None,
        output_tokens=int(out) if isinstance(out, int) else None,
    )


class ClaudeCodeBackend(AgentBackend):
    """The default backend: the Claude Code CLI run headless inside a prepared workspace."""

    name = "claude-code"

    def __init__(self, cli: str = "claude") -> None:
        # The CLI binary, resolved through PATH. Overridable so a test can point at a stub and so a
        # deployment can pin an absolute path.
        self.cli = cli

    def health(self) -> BackendHealth:
        """Report whether the Claude Code CLI is installed and the Anthropic key is configured.

        Installed is probed by running the CLI's version flag; authed is whether the server side
        ANTHROPIC_API_KEY is set. Neither step runs an agent task or makes a model call.
        """
        installed, detail = self._probe_cli()
        authed = bool(get_settings().anthropic_api_key)
        if not authed and installed:
            detail = "ANTHROPIC_API_KEY is not set in the server environment"
        return BackendHealth(backend=self.name, installed=installed, authed=authed, detail=detail)

    def _probe_cli(self) -> tuple[bool, str]:
        try:
            proc = subprocess.run(
                [self.cli, "--version"],
                capture_output=True,
                text=True,
                timeout=_PROBE_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            return False, f"{self.cli} CLI not found on PATH"
        except (subprocess.TimeoutExpired, OSError) as exc:
            return False, f"{self.cli} CLI did not start: {type(exc).__name__}"
        if proc.returncode != 0:
            return False, (proc.stderr or proc.stdout or "").strip()[:200]
        return True, (proc.stdout or "").strip()[:200]

    def _compose_prompt(self, task: str, context: str | None) -> str:
        """Build the agent prompt from the task and optional grounding context.

        The prompt carries only the work to do. No provider key, credential, or server secret is
        ever placed here; the key reaches the CLI through its environment, never its prompt.
        """
        task = (task or "").strip()
        context = (context or "").strip()
        if context:
            return f"{context}\n\nTask:\n{task}"
        return task

    def _cli_argv(self, prompt: str, autonomy: int) -> list[str]:
        """The headless CLI invocation. Edits are auto accepted because the workspace is a sandbox
        and the real commit or reject decision is the downstream gate's, not the agent's. Autonomy
        bounds the number of turns the agent may take, a light leash; it does not gate the diff."""
        max_turns = max(4, 6 + autonomy * 4)
        return [
            self.cli,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--permission-mode",
            "acceptEdits",
            "--max-turns",
            str(max_turns),
        ]

    def run(
        self,
        task: str,
        workspace: Workspace,
        *,
        context: str | None = None,
        autonomy: int = 0,
        timeout: int | None = None,
    ) -> AgentResult:
        """Run the task with Claude Code inside the workspace and return the proposed change.

        The workspace path is re validated under the builds root, the CLI runs headless with that
        directory as its cwd and the Anthropic key injected into its environment, and the resulting
        edits are captured as a diff. Nothing is committed and nothing outside the workspace is
        touched. The key value is redacted from every returned string.
        """
        if workspace is None:
            raise BackendError("a backend run requires a workspace")
        try:
            path = ensure_within_root(builds_root(), workspace.path)
        except PathSafetyError as exc:
            raise BackendError(f"workspace path is outside the builds root: {exc}") from exc
        if not path.is_dir():
            raise BackendError(f"workspace directory does not exist: {path}")

        api_key = get_settings().anthropic_api_key
        prompt = self._compose_prompt(task, context)
        argv = self._cli_argv(prompt, autonomy)
        run_timeout = timeout if timeout is not None else DEFAULT_AGENT_TIMEOUT_SECONDS

        timed_out = False
        try:
            proc = subprocess.run(
                argv,
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=run_timeout,
                env=_cli_env(api_key),
            )
            exit_code: int | None = proc.returncode
            stdout, stderr = proc.stdout or "", proc.stderr or ""
        except FileNotFoundError as exc:
            raise BackendError(f"{self.cli} CLI not found on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = None
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""

        # Capture whatever the agent left in the workspace, even after a timeout: the partial edits
        # are still the proposed change for the gate to see.
        diff, files_changed = self._capture_diff(workspace)
        parsed = _parse_output(stdout)
        transcript = self._format_transcript(argv, exit_code, timed_out, stdout, stderr)

        return AgentResult(
            backend=self.name,
            diff=_redact(diff, api_key),
            files_changed=files_changed,
            transcript=_redact(transcript, api_key),
            reasoning=_redact(parsed.reasoning, api_key),
            exit_code=exit_code,
            timed_out=timed_out,
            cost_usd=parsed.cost_usd,
            input_tokens=parsed.input_tokens,
            output_tokens=parsed.output_tokens,
        )

    def _capture_diff(self, workspace: Workspace) -> tuple[str, list[str]]:
        """Capture the agent's uncommitted edits as a unified diff and a changed file list.

        The changed files are read from git status before any staging, so untracked files the agent
        created are included. Intent to add then makes those new files show their content in git
        diff. Every git command runs through the guarded runner, which re validates the workspace
        path and refuses anything that escapes it.
        """
        status = run_in_workspace(
            workspace, ["git", "status", "--porcelain"], timeout=_GIT_TIMEOUT_SECONDS
        )
        files_changed = _parse_porcelain(status.stdout)
        # Intent to add surfaces new files in the diff without staging their content for commit.
        run_in_workspace(workspace, ["git", "add", "-A", "-N"], timeout=_GIT_TIMEOUT_SECONDS)
        diff = run_in_workspace(workspace, ["git", "diff"], timeout=_GIT_TIMEOUT_SECONDS)
        return diff.stdout, files_changed

    def _format_transcript(
        self, argv: list[str], exit_code: int | None, timed_out: bool, stdout: str, stderr: str
    ) -> str:
        """Assemble the run record: the invocation header plus the captured output. The prompt in
        argv may be long, so it is summarised to its head rather than printed whole."""
        shown = list(argv)
        if "-p" in shown:
            i = shown.index("-p")
            if i + 1 < len(shown):
                prompt = shown[i + 1]
                shown[i + 1] = prompt[:120] + ("..." if len(prompt) > 120 else "")
        header = f"$ {' '.join(shown)}"
        status = "timed out" if timed_out else f"exit {exit_code}"
        parts = [header, f"[{status}]"]
        if stdout.strip():
            parts.append("--- stdout ---\n" + stdout.strip())
        if stderr.strip():
            parts.append("--- stderr ---\n" + stderr.strip())
        return "\n".join(parts)
