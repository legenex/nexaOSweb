"""The worker boundary: dispatch a run as a job, decoupled from the request serving Brain.

The engine never executes a run inline in a request handler. It hands the run to a BuildWorker as a
Job, so build execution lives behind an interface that a real queue or a separate worker process can
replace without touching the engine. In dev the default is InProcessWorker, which runs the job
synchronously and returns its result, which is enough to prove the box end to end before a queue is
introduced.

A Job carries a name, an optional run id for correlation, and the work itself as a thunk (a zero
argument callable). The worker runs the thunk and returns a JobResult: ok with the value, or not ok
with the error text. Exceptions are captured into the result rather than raised, so a single failing
job never takes the worker down.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class Job:
    """One unit of build work handed to the worker.

    run is the thunk the worker executes. run_id correlates the job back to an AgentRun when the
    engine later dispatches real runs; it carries no logic in the worker itself.
    """

    name: str
    run: Callable[[], Any]
    run_id: int | None = None


@dataclass
class JobResult:
    """The outcome of a dispatched job: its value, or the error that ended it."""

    name: str
    ok: bool
    run_id: int | None = None
    value: Any = None
    error: str | None = None


class BuildWorker(ABC):
    """The boundary the engine dispatches through. Implementations decide where work runs."""

    @abstractmethod
    def submit(self, job: Job) -> JobResult:
        """Dispatch a job and return its result."""
        raise NotImplementedError


class InProcessWorker(BuildWorker):
    """The dev default: run the job synchronously in the current process and return its result.

    It is deliberately the simplest possible worker. A real deployment swaps this for a queue
    backed worker that runs on the dedicated build worker, never on the Plesk Brain, with no change
    to the engine that dispatches through the BuildWorker interface.
    """

    def submit(self, job: Job) -> JobResult:
        try:
            value = job.run()
        except Exception as exc:  # noqa: BLE001 - the boundary captures every failure as a result
            return JobResult(
                name=job.name, ok=False, run_id=job.run_id, error=f"{type(exc).__name__}: {exc}"
            )
        return JobResult(name=job.name, ok=True, run_id=job.run_id, value=value)


# The process wide default worker. A later milestone resolves this from settings so a queue backed
# worker can be selected for production without touching the call sites.
_default_worker: BuildWorker = InProcessWorker()


def get_worker() -> BuildWorker:
    """Return the configured build worker. In dev this is the in process synchronous worker."""
    return _default_worker
