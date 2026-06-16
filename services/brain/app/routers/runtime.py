"""Runtime read and aggregation endpoints.

Reads only. The runtime ledger is authored solely through the four writers in app/runtime.py;
no protected field is writable over HTTP, by design there is no write route here. Every
endpoint is a pure projection or aggregation of stored truth: a run with its steps, steps after
a cursor, approval candidates, failed steps, proof of work per step, runs per project, the
active runs, and per status counts.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.access import user_owns_project as _user_owns_project
from app.db import get_db
from app.gates import recommend_gate
from app.models.runtime import AgentRun, AgentStep
from app.models.user import User
from app.runtime import (
    ACTIVE_RUN_STATUSES,
    COMPLETED_VERIFIED,
    FAILED,
    WAITING_APPROVAL,
    RuntimeWriteError,
    resolve_approval,
)
from app.schemas.runtime import (
    ApprovalRequest,
    ProofOfWork,
    ResolveApprovalRequest,
    RunRead,
    RunWithSteps,
    StepRead,
)
from app.security.auth import current_user

router = APIRouter(prefix="/runtime", tags=["runtime"])


def _load_run(run_id: int, user: User, db: Session) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None or not _user_owns_project(run.project_id, user, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return run


def _ordered_steps(db: Session, run_id: int) -> list[AgentStep]:
    return (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run_id)
        .order_by(AgentStep.seq.asc(), AgentStep.id.asc())
        .all()
    )


@router.get("/runs", response_model=list[RunRead])
def list_runs(
    project_id: int | None = Query(None),
    active: bool = Query(False),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[AgentRun]:
    query = db.query(AgentRun)
    if project_id is not None:
        if not _user_owns_project(project_id, user, db):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
        query = query.filter(AgentRun.project_id == project_id)
    if active:
        query = query.filter(AgentRun.status.in_(tuple(ACTIVE_RUN_STATUSES)))
    runs = query.order_by(AgentRun.created_at.desc(), AgentRun.id.desc()).all()
    # Scope to runs the user may see (covers the no-project and owned-project cases).
    return [run for run in runs if _user_owns_project(run.project_id, user, db)]


@router.get("/runs/{run_id}", response_model=RunWithSteps)
def get_run(
    run_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RunWithSteps:
    run = _load_run(run_id, user, db)
    steps = _ordered_steps(db, run_id)
    return RunWithSteps(
        **RunRead.model_validate(run).model_dump(),
        steps=[StepRead.model_validate(step) for step in steps],
    )


@router.get("/runs/{run_id}/steps", response_model=list[StepRead])
def list_steps_after_cursor(
    run_id: int,
    after: int | None = Query(
        None, description="a step id; defaults to the run's cursor_step_id when omitted"
    ),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[AgentStep]:
    run = _load_run(run_id, user, db)
    cursor_step_id = after if after is not None else run.cursor_step_id
    after_seq = -1
    if cursor_step_id is not None:
        cursor = db.get(AgentStep, cursor_step_id)
        if cursor is not None and cursor.run_id == run.id:
            after_seq = cursor.seq
    return [step for step in _ordered_steps(db, run_id) if step.seq > after_seq]


@router.get("/runs/{run_id}/approvals", response_model=list[ApprovalRequest])
def list_approval_candidates(
    run_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ApprovalRequest]:
    _load_run(run_id, user, db)
    gated = [step for step in _ordered_steps(db, run_id) if step.status == WAITING_APPROVAL]
    return [
        ApprovalRequest(**StepRead.model_validate(step).model_dump(), **recommend_gate(step))
        for step in gated
    ]


@router.post("/steps/{step_id}/resolve", response_model=StepRead)
def resolve_step(
    step_id: int,
    payload: ResolveApprovalRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AgentStep:
    """Resolve a waiting_approval step. The single human gate write into the runtime.

    Delegates to the resolve_approval writer, which owns only the approval exit edges (approve
    moves to planned, reject to skipped). Resolving anything not at the gate is a conflict.
    """
    step = db.get(AgentStep, step_id)
    if step is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "step not found")
    _load_run(step.run_id, user, db)  # ownership gate via the parent run
    try:
        return resolve_approval(
            db,
            step,
            resolution=payload.resolution,
            resolved_by=user.email or "user",
            note=payload.note,
        )
    except RuntimeWriteError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/runs/{run_id}/failed", response_model=list[StepRead])
def list_failed_steps(
    run_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[AgentStep]:
    _load_run(run_id, user, db)
    return [step for step in _ordered_steps(db, run_id) if step.status == FAILED]


@router.get("/runs/{run_id}/status-counts", response_model=dict[str, int])
def step_status_counts(
    run_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    _load_run(run_id, user, db)
    counts: dict[str, int] = {}
    for step in _ordered_steps(db, run_id):
        counts[step.status] = counts.get(step.status, 0) + 1
    return counts


@router.get("/steps/{step_id}/proof", response_model=ProofOfWork)
def step_proof_of_work(
    step_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProofOfWork:
    step = db.get(AgentStep, step_id)
    if step is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "step not found")
    _load_run(step.run_id, user, db)  # ownership gate via the parent run
    evidence = list(step.evidence or [])
    tool_count = sum(1 for item in evidence if item.get("source") == "tool")
    return ProofOfWork(
        step_id=step.id,
        status=step.status,
        verified=step.status == COMPLETED_VERIFIED,
        evidence_count=len(evidence),
        tool_evidence_count=tool_count,
        evidence=evidence,
        tool_call=step.tool_call,
    )
