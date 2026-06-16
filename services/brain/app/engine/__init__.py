"""The Agent Build Engine execution layer: the safe box every agent run uses.

This package is the isolated execution layer described in docs/ARCHITECTURE.md under "Agent
Build Engine". It holds no agent calls yet, only the sandbox the engine will later drive:

  - workspace: prepare an isolated working directory per project under NEXA_RUNTIME_ROOT (the single
    agent execution root, shared with the executor's worktrees), through the path safety gate, with
    the target git repo cloned or initialised inside it.
  - runner: run a bounded shell command inside a workspace, capturing stdout, stderr, and an exit
    code, and refusing anything that would leave the workspace, force push, or push a protected
    branch.
  - worker: the boundary that dispatches a run as a job, so the engine is decoupled from the
    request serving Brain. An in process synchronous worker is the dev default behind an interface
    a real queue or separate worker process can replace.
  - backends: the AgentBackend interface and its adapters, wrapping each external coding CLI behind
    one shape (health, run) so the orchestrator drives any backend the same way. Claude Code is the
    default and first adapter; it runs headless inside a workspace and returns the proposed diff.
"""

from app.engine.backends import (
    DEFAULT_AGENT_TIMEOUT_SECONDS,
    DEFAULT_BACKEND,
    AgentBackend,
    AgentResult,
    BackendError,
    BackendHealth,
    ClaudeCodeBackend,
    available_backends,
    get_backend,
)
from app.engine.runner import (
    DEFAULT_TIMEOUT_SECONDS,
    CommandRefused,
    CommandResult,
    run_in_workspace,
)
from app.engine.worker import (
    BuildWorker,
    InProcessWorker,
    Job,
    JobResult,
    get_worker,
)
from app.engine.workspace import (
    Workspace,
    WorkspaceError,
    builds_root,
    prepare_workspace,
)

__all__ = [
    "Workspace",
    "WorkspaceError",
    "builds_root",
    "prepare_workspace",
    "CommandResult",
    "CommandRefused",
    "run_in_workspace",
    "DEFAULT_TIMEOUT_SECONDS",
    "BuildWorker",
    "InProcessWorker",
    "Job",
    "JobResult",
    "get_worker",
    "AgentBackend",
    "AgentResult",
    "BackendError",
    "BackendHealth",
    "ClaudeCodeBackend",
    "DEFAULT_AGENT_TIMEOUT_SECONDS",
    "DEFAULT_BACKEND",
    "available_backends",
    "get_backend",
]
