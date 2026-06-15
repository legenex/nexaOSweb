"""The Agent Build Engine execution layer: the safe box every agent run uses.

This package is the isolated execution layer described in docs/ARCHITECTURE.md under "Agent
Build Engine". It holds no agent calls yet, only the sandbox the engine will later drive:

  - workspace: prepare an isolated working directory per project under NEXA_BUILDS_ROOT, through
    the path safety gate, with the target git repo cloned or initialised inside it.
  - runner: run a bounded shell command inside a workspace, capturing stdout, stderr, and an exit
    code, and refusing anything that would leave the workspace, force push, or push a protected
    branch.
  - worker: the boundary that dispatches a run as a job, so the engine is decoupled from the
    request serving Brain. An in process synchronous worker is the dev default behind an interface
    a real queue or separate worker process can replace.
"""

from app.engine.runner import (
    DEFAULT_TIMEOUT_SECONDS,
    CommandRefused,
    CommandResult,
    run_in_workspace,
)
from app.engine.workspace import (
    Workspace,
    WorkspaceError,
    builds_root,
    prepare_workspace,
)
from app.engine.worker import (
    BuildWorker,
    InProcessWorker,
    Job,
    JobResult,
    get_worker,
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
]
