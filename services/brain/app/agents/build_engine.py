"""The Agent Build Engine: drive an external coding agent through the executor's gated spine.

This is the prove-it milestone for the engine: one task, one backend (claude-code), one gated run,
proven end to end in dev through the in-process worker. It reuses the executor, it does not
reimplement it. A build run is an AgentRun of the executor kind discriminated by a non-null backend.
The external agent performs the edit phase inside the executor's own worktree; every step after that
is the proven executor path:

    start  -> open the executor worktree, run the claude-code backend in it through the worker,
              record the agent's work as a build step, then reuse compute_diff_step and
              request_approval to park the run at the human gate (awaiting review).
    approve -> resolve the gate, then reuse merge_on_approval to promote the diff into the served
               project repo. Never a new merge, never a force, never a protected branch.
    reject  -> resolve the gate rejected and discard the diff through the existing rollback path,
               returning the task to its prior status.
    cancel  -> stop an active run and return the task to its prior status.

The provider key is read from server settings only by the backend and injected straight into the
CLI process; it never enters the prompt, the ledger, or any response. The task flips to
agent_working while the run is live and back to a review or its prior status when the gate resolves.
"""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.agents.executor import (
    APPROVAL_STEP_KIND,
    DIFF_STEP_KIND,
    EXECUTOR_AUTONOMY,
    EXECUTOR_KIND,
    MERGE_STEP_KIND,
    PHASE_GATE,
    ExecutorError,
    compute_diff_step,
    merge_on_approval,
    open_run_workspace,
    request_approval,
    rollback_executor_run,
)
from app.engine import (
    DEFAULT_AGENT_TIMEOUT_SECONDS,
    DEFAULT_BACKEND,
    AgentResult,
    BackendError,
    Job,
    Workspace,
    get_backend,
    get_worker,
)
from app.gates import SAFE_TAGS
from app.models.project import Project
from app.models.runtime import AgentRun, AgentStep
from app.models.workspace import Task
from app.runtime import (
    ACTIVE_RUN_STATUSES,
    COMPLETED_UNVERIFIED,
    COMPLETED_VERIFIED,
    WAITING_APPROVAL,
    create_run,
    propose_step,
    record_execution,
    resolve_approval,
)
from app.safety import ensure_within_root, safe_write_text
from app.settings import get_settings

logger = logging.getLogger(__name__)

# A build run is an executor-kind run; the external agent's work is recorded as this step kind. It
# sits alongside the executor's own plan, edit, check, diff, and merge step kinds in the ledger.
BUILD_STEP_KIND = "agent_build"

# The build run lifecycle markers stored on AgentRun.phase. build while the agent edits, then the
# executor's gate marker once parked for review. rejected, cancelled, and failed are the terminal
# build outcomes that did not merge; the executor's merged and rolled_back cover the approved paths.
PHASE_BUILD = "build"
PHASE_REJECTED = "rejected"
PHASE_CANCELLED = "cancelled"
PHASE_FAILED = "failed"

# The agent's edits live inside the isolated worktree: reversible, local, external to nothing, so
# the build step is classified safe and lands planned rather than at the gate. The single human gate
# is the executor's approval_request, parked before anything leaves the worktree.
_BUILD_RISK = {tag: True for tag in SAFE_TAGS}

# The terminal completed states a recorded step lands on.
_COMPLETED_STATES = (COMPLETED_VERIFIED, COMPLETED_UNVERIFIED)

# How much of the spilled diff and transcript the detail read returns. The full text is always on
# disk under the runtime root; the response is capped so a huge diff cannot blow up a payload.
_DETAIL_DIFF_CAP = 200_000
_DETAIL_TRANSCRIPT_CAP = 100_000
_PREVIEW_CHARS = 500


class BuildEngineError(Exception):
    """Raised when a build run cannot be started or driven (bad input, no project, no backend)."""


class BackendUnavailableError(BuildEngineError):
    """Raised when the requested backend's CLI is not installed or not authed in the environment."""


# --- spill and read helpers (the runtime root, the single agent execution root) -----------


def _runtime_root() -> Path:
    return Path(get_settings().nexa_runtime_root).expanduser().resolve()


def _spill_text(run_id: int, relative: str, content: str) -> dict:
    """Write text under the runtime root and return a content reference, never the inline body."""
    rel = str(Path(f"run_{run_id}") / relative)
    safe_write_text(_runtime_root(), rel, content)
    return {
        "ref": rel,
        "bytes": len(content.encode("utf-8")),
        "preview": content[:_PREVIEW_CHARS],
    }


def _read_spilled(ref: str | None, cap: int) -> str:
    """Read a spilled file by its runtime-root-relative ref, path gated and capped. Missing is ''.

    A bad or absent ref returns an empty string so a read endpoint never breaks on it.
    """
    if not ref:
        return ""
    try:
        path = ensure_within_root(_runtime_root(), ref)
    except Exception:  # noqa: BLE001 - a bad ref never breaks a read endpoint
        return ""
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:cap]


# --- run and step lookups -----------------------------------------------------------------


def is_build_run(run: AgentRun) -> bool:
    """A build run is an executor-kind run an external backend drove (a non-null backend)."""
    return run.backend is not None


def _latest_step_of_kind(db: Session, run: AgentRun, kind: str) -> AgentStep | None:
    return (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run.id, AgentStep.kind == kind)
        .order_by(AgentStep.seq.desc(), AgentStep.id.desc())
        .first()
    )


def _open_gate_step(db: Session, run: AgentRun) -> AgentStep | None:
    """The approval_request step parked at the human gate, if the run is still awaiting review."""
    return (
        db.query(AgentStep)
        .filter(
            AgentStep.run_id == run.id,
            AgentStep.kind == APPROVAL_STEP_KIND,
            AgentStep.status == WAITING_APPROVAL,
        )
        .order_by(AgentStep.seq.desc(), AgentStep.id.desc())
        .first()
    )


def _has_completed_merge(db: Session, run: AgentRun) -> bool:
    merge = _latest_step_of_kind(db, run, MERGE_STEP_KIND)
    return merge is not None and merge.status in _COMPLETED_STATES


def _run_task(db: Session, run: AgentRun) -> Task | None:
    if run.task_id is None:
        return None
    return db.get(Task, run.task_id)


def _task_prior_status(run: AgentRun) -> str:
    build = run.plan.get("build", {}) if isinstance(run.plan, dict) else {}
    prior = build.get("task_prior_status")
    return prior if isinstance(prior, str) and prior else "todo"


# --- the prompt ---------------------------------------------------------------------------


def _build_prompt(task: Task) -> str:
    """The instruction handed to the agent as its prompt. No key or secret is ever placed here."""
    lines = [
        "Build this task by editing files directly in the current working directory, which is an "
        "isolated git worktree of the project. Make the change, then stop. Do not run git commit; "
        "leave your edits uncommitted so they can be reviewed.",
        "",
        f"Task: {task.title}",
    ]
    if task.detail:
        lines += ["", str(task.detail)]
    if task.goal_for_agent:
        lines += ["", f"Goal: {task.goal_for_agent}"]
    return "\n".join(lines)


# --- recording the agent's work as a step -------------------------------------------------


def _record_build_step(
    db: Session,
    run: AgentRun,
    *,
    agent_result: AgentResult | None = None,
    error: str | None = None,
) -> AgentStep:
    """Record the external agent's run as a build step, the honest ledger of what it did.

    The transcript is spilled under the runtime root and referenced; only a short preview is inline.
    A clean run lands the step completed with tool evidence; a failed or errored run lands failed.
    """
    if agent_result is not None:
        spilled = _spill_text(run.id, "build/transcript.txt", agent_result.transcript or "")
        ok = agent_result.ok
        backend_name = agent_result.backend
        files = list(agent_result.files_changed)
        evidence = [
            {
                "source": "tool",
                "tool": "agent_backend",
                "backend": agent_result.backend,
                "exit_code": agent_result.exit_code,
                "timed_out": agent_result.timed_out,
                "files_changed": files,
                "reasoning": agent_result.reasoning,
                "cost_usd": agent_result.cost_usd,
                "input_tokens": agent_result.input_tokens,
                "output_tokens": agent_result.output_tokens,
                "transcript_ref": spilled["ref"],
                "transcript_bytes": spilled["bytes"],
                "transcript_preview": spilled["preview"],
            }
        ]
    else:
        spilled = _spill_text(run.id, "build/transcript.txt", error or "")
        ok = False
        backend_name = run.backend or DEFAULT_BACKEND
        files = []
        evidence = [
            {
                "source": "tool",
                "tool": "agent_backend",
                "backend": backend_name,
                "error": error,
                "transcript_ref": spilled["ref"],
                "transcript_bytes": spilled["bytes"],
                "transcript_preview": spilled["preview"],
            }
        ]

    step = propose_step(
        db,
        run,
        kind=BUILD_STEP_KIND,
        title=f"Agent build via {backend_name}",
        intent="External coding agent edited the isolated worktree to build the task.",
        payload={
            "build": {"backend": backend_name, "files": files, "ok": ok},
            "risk": dict(_BUILD_RISK),
        },
        proposed_by="system",
    )
    failure = None if ok else {"reason": "agent backend run did not complete", "error": error}
    record_execution(
        db, step, outcome=("completed" if ok else "failed"), evidence=evidence, failure=failure
    )
    return step


# --- starting a build run -----------------------------------------------------------------


def start_build_run(
    db: Session,
    *,
    task: Task,
    backend_name: str | None = None,
    proposed_by: str = "user",
    timeout: int = DEFAULT_AGENT_TIMEOUT_SECONDS,
) -> AgentRun:
    """Start a gated build run for one task and park it at the human gate.

    The task must belong to a project (the worktree and the merge target). The backend must be
    available in this environment (the CLI installed and the key set, server side). The run opens
    the executor's worktree, the agent edits inside it through the in-process worker, the diff is
    captured and the run parks at awaiting review. The task flips to agent_working for the run. On a
    backend failure the task returns to its prior status and the run is recorded failed.
    """
    if task.project_id is None:
        raise BuildEngineError("a build run requires the task to belong to a project")
    project = db.get(Project, task.project_id)
    if project is None:
        raise BuildEngineError("project not found for the task")

    name = (backend_name or DEFAULT_BACKEND).strip()
    try:
        backend = get_backend(name)
    except BackendError as exc:
        raise BuildEngineError(str(exc)) from exc
    health = backend.health()
    if not health.available:
        raise BackendUnavailableError(
            f"backend '{name}' is not available in this environment: {health.detail}"
        )

    prior_status = task.status
    run = create_run(
        db,
        project_id=project.id,
        autonomy_level=EXECUTOR_AUTONOMY,
        kind=EXECUTOR_KIND,
        plan={
            "build": {
                "task_id": task.id,
                "task_prior_status": prior_status,
                "backend": name,
            }
        },
        goal_summary=(task.goal_for_agent or task.title or "Agent build run")[:2000],
        proposed_by=proposed_by,
    )
    run.backend = name
    run.task_id = task.id

    branch_ref, worktree_path = open_run_workspace(project, run.id)
    run.branch_ref = branch_ref
    run.worktree_path = str(worktree_path)
    run.phase = PHASE_BUILD
    db.commit()
    db.refresh(run)

    # Flip the task to agent_working and link it to the run while the agent works.
    task.status = "agent_working"
    task.run_id = run.id
    db.commit()

    workspace = Workspace(
        project_id=project.id, slug=project.slug, path=worktree_path, repo_url=None
    )
    prompt = _build_prompt(task)
    job = Job(
        name=f"agent-build-run-{run.id}",
        run_id=run.id,
        run=lambda: backend.run(prompt, workspace, autonomy=run.autonomy_level, timeout=timeout),
    )
    job_result = get_worker().submit(job)

    if not job_result.ok or job_result.value is None:
        _record_build_step(db, run, error=job_result.error or "the backend produced no result")
        return _fail_run(db, run, task, prior_status)

    agent_result: AgentResult = job_result.value
    _record_build_step(db, run, agent_result=agent_result)
    run.reasoning_summary = (agent_result.reasoning or "")[:4000]
    run.cost_usd = agent_result.cost_usd
    db.commit()

    if not agent_result.ok:
        return _fail_run(db, run, task, prior_status)

    # Reuse the executor's diff capture and human gate, unchanged.
    compute_diff_step(db, run)
    request_approval(
        db, run, checks_summary={"passed": [], "failed": [], "cannot_run": []}
    )
    run.phase = PHASE_GATE
    db.commit()
    db.refresh(run)
    return run


def _fail_run(db: Session, run: AgentRun, task: Task, prior_status: str) -> AgentRun:
    """Record a failed build run: mark the phase failed and return the task to its prior status."""
    run.phase = PHASE_FAILED
    db.commit()
    if task is not None and task.deleted_at is None:
        task.status = prior_status
        db.commit()
    db.refresh(run)
    return run


# --- resolving a build run: approve, reject, cancel ---------------------------------------


def _require_build_run(run: AgentRun) -> None:
    if not is_build_run(run):
        raise BuildEngineError("not a build run")


def approve_build_run(db: Session, run: AgentRun, *, resolved_by: str = "user") -> AgentRun:
    """Approve the gate and promote the diff through the executor's existing merge path.

    The open gate is resolved approved, then merge_on_approval commits the worktree and merges its
    branch into the served project repo (a no-ff merge, never a force, never a protected source
    branch). The task moves to review.
    """
    _require_build_run(run)
    gate = _open_gate_step(db, run)
    if gate is None:
        raise BuildEngineError("this run has no open gate to approve")
    resolve_approval(db, gate, resolution="approved", resolved_by=resolved_by)
    try:
        merge_on_approval(db, run, proposed_by="system")
    except ExecutorError as exc:
        raise BuildEngineError(str(exc)) from exc

    task = _run_task(db, run)
    if task is not None and task.deleted_at is None:
        task.status = "review"
        db.commit()
    db.refresh(run)
    return run


def reject_build_run(db: Session, run: AgentRun, *, resolved_by: str = "user") -> AgentRun:
    """Reject the gate and discard the diff, returning the task to its prior status.

    The open gate is resolved rejected so nothing leaves the worktree. If a merge had somehow
    already landed, it is reverted through the existing rollback path. The task returns to the
    status it held before the run started.
    """
    _require_build_run(run)
    gate = _open_gate_step(db, run)
    if gate is not None:
        resolve_approval(db, gate, resolution="rejected", resolved_by=resolved_by)
    if _has_completed_merge(db, run):
        rollback_executor_run(db, run, proposed_by="system")
    else:
        run.phase = PHASE_REJECTED
        db.commit()

    task = _run_task(db, run)
    if task is not None and task.deleted_at is None:
        task.status = _task_prior_status(run)
        db.commit()
    db.refresh(run)
    return run


def cancel_build_run(db: Session, run: AgentRun, *, resolved_by: str = "user") -> AgentRun:
    """Cancel an active build run and return the task to its prior status.

    Cancel applies only while the run is active (running or awaiting review). Any open gate is
    resolved rejected so nothing leaves the worktree, the run is marked cancelled, and the task
    returns to the status it held before the run started.
    """
    _require_build_run(run)
    if run.status not in ACTIVE_RUN_STATUSES:
        raise BuildEngineError("only an active run can be cancelled")
    gate = _open_gate_step(db, run)
    if gate is not None:
        resolve_approval(db, gate, resolution="rejected", resolved_by=resolved_by)
    run.phase = PHASE_CANCELLED
    db.commit()

    task = _run_task(db, run)
    if task is not None and task.deleted_at is None:
        task.status = _task_prior_status(run)
        db.commit()
    db.refresh(run)
    return run


# --- the read projection ------------------------------------------------------------------


def build_run_detail(db: Session, run: AgentRun) -> dict:
    """Assemble the review payload for a build run: diff, transcript, reasoning, backend, cost.

    The diff comes from the executor's diff step (the same source an executor run surfaces), the
    transcript from the build step, both read from their spilled files under the runtime root and
    capped. gate_step_id is the open human gate when the run is awaiting review, else null.
    """
    diff_step = _latest_step_of_kind(db, run, DIFF_STEP_KIND)
    diff_text = ""
    diff_shortstat = ""
    diff_capped = False
    if diff_step is not None:
        payload = diff_step.payload.get("diff", {}) if isinstance(diff_step.payload, dict) else {}
        diff_shortstat = str(payload.get("shortstat", ""))
        diff_capped = bool(payload.get("capped", False))
        evidence = diff_step.evidence[0] if diff_step.evidence else {}
        diff_text = _read_spilled(evidence.get("diff_ref"), _DETAIL_DIFF_CAP)

    build_step = _latest_step_of_kind(db, run, BUILD_STEP_KIND)
    transcript = ""
    files_changed: list[str] = []
    if build_step is not None:
        evidence = build_step.evidence[0] if build_step.evidence else {}
        transcript = _read_spilled(evidence.get("transcript_ref"), _DETAIL_TRANSCRIPT_CAP)
        files_changed = list(evidence.get("files_changed", []) or [])

    gate = _open_gate_step(db, run)
    return {
        "id": run.id,
        "project_id": run.project_id,
        "task_id": run.task_id,
        "status": run.status,
        "kind": run.kind,
        "phase": run.phase,
        "backend": run.backend,
        "reasoning_summary": run.reasoning_summary,
        "cost_usd": run.cost_usd,
        "goal_summary": run.goal_summary,
        "diff": diff_text,
        "diff_shortstat": diff_shortstat,
        "diff_capped": diff_capped,
        "transcript": transcript,
        "files_changed": files_changed,
        "gate_step_id": gate.id if gate is not None else None,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "finished_at": run.finished_at,
    }
