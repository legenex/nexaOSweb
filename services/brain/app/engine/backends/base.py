"""The AgentBackend interface: one shape for every external coding agent the engine drives.

The Agent Build Engine drives external coding CLIs (Claude Code, Codex CLI, Grok Build). Each is
wrapped behind this one interface so the orchestrator opens a workspace, hands over a task, and gets
back a diff the same way regardless of which backend ran, in the same spirit as the model router:
the backend is a config and adapter choice, never a hardcoded branch in business logic.

Two things every backend exposes:

  - health(): a probe that reports whether the CLI is installed and authed, without running a task.
  - run(): execute one task inside a prepared workspace and return an AgentResult: the proposed
    diff, the files it touched, the command transcript, a short reasoning summary, the exit status,
    a token or cost estimate, and the backend name.

A backend never commits. It proposes a diff inside the workspace; a deterministic gate downstream
(not the agent) decides whether to commit or reject it. A backend never receives a provider key in
its task prompt and never returns one to any client: keys are read from the server environment only
and injected straight into the CLI process by the adapter, never through the task text.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.engine.workspace import Workspace


class BackendError(Exception):
    """Raised when a backend cannot run a task (a missing workspace, a CLI that will not start)."""


@dataclass
class BackendHealth:
    """Whether a backend can run right now, reported without executing a task.

    enabled is whether the backend is turned on at all: a feature flagged backend (for example Grok
    Build behind NEXA_ENABLE_GROK) reports enabled false while its flag is off, so it is never
    dispatched to and its health says disabled without probing a CLI. installed is whether the CLI
    binary is present and starts. authed is whether the server side credential the CLI needs is
    configured. available is the conjunction: a backend the engine may actually dispatch to. detail
    carries a short human readable note (a version string, or why it is unavailable or disabled) and
    never contains a secret value.
    """

    backend: str
    installed: bool
    authed: bool
    detail: str = ""
    enabled: bool = True

    @property
    def available(self) -> bool:
        return self.enabled and self.installed and self.authed


@dataclass
class AgentResult:
    """The outcome of one backend run, the unit the orchestrator records and gates on.

    diff is the proposed unified diff captured from the workspace after the agent edited it; nothing
    is committed. files_changed lists the workspace relative paths the agent touched. transcript is
    the record of the CLI invocation (argv header plus its captured output), with any provider key
    value redacted. reasoning is a short summary of what the agent did. exit_code and timed_out
    carry the process status. cost_usd, input_tokens, and output_tokens are the estimate the CLI
    reported, or None when it did not. backend is the adapter name that produced this result.
    """

    backend: str
    diff: str
    files_changed: list[str] = field(default_factory=list)
    transcript: str = ""
    reasoning: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def ok(self) -> bool:
        """True when the agent process completed cleanly. A clean run with an empty diff is still
        ok; whether an empty diff is acceptable is a decision for the gate, not the backend."""
        return self.exit_code == 0 and not self.timed_out


class AgentBackend(ABC):
    """The one interface every external coding agent is driven through.

    name is the stable config key the backend is selected by (for example "claude-code"). An
    implementation wraps a single CLI: it probes health without side effects, and runs a task inside
    a prepared workspace, writing only within that workspace and returning an AgentResult.
    """

    name: str = "agent-backend"

    @abstractmethod
    def health(self) -> BackendHealth:
        """Report whether this backend's CLI is installed and authed, without running a task."""
        raise NotImplementedError

    @abstractmethod
    def run(
        self,
        task: str,
        workspace: Workspace,
        *,
        context: str | None = None,
        autonomy: int = 0,
        timeout: int | None = None,
    ) -> AgentResult:
        """Run one task inside the workspace and return the proposed change as an AgentResult.

        task is the instruction handed to the agent as its prompt. context is optional grounding
        prepended to the prompt (for example the project requirements). autonomy is the run's
        autonomy level (0 to 4); the backend may use it to bound the agent, but the commit or reject
        decision always belongs to the downstream gate, never the backend. timeout caps the run.

        The agent writes only inside the workspace. Provider keys are never placed in task, context,
        or the returned result.
        """
        raise NotImplementedError
