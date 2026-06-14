"""Agent runtime authorship: the four writers, the transition table, and the derivations.

This is the only write path into the runtime ledger, and it is deliberately split so no single
function can author a step end to end. Each writer owns one boundary of a step's life:

    propose_step       intent only, and the entry gate (planned, or waiting_approval at autonomy 0)
    record_execution   outcome, evidence, tool_call, failure; derives verified from evidence
    resolve_approval   the approval exit edges only (approve -> planned, reject -> skipped)
    correct_step       terminal status corrections only (status, correction_note, corrected_from)

completed_verified is never a target a caller may request. record_execution derives it, and only
when a completed step carries at least one tool sourced evidence item. Terminal states change
only through correct_step, never through record_execution. The cached AgentRun.status is a pure
derivation of its steps, refreshed after every writer call.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.gates import can_auto_resolve
from app.models.base import utcnow
from app.models.runtime import AgentRun, AgentStep
from app.safety import safe_write_text
from app.settings import get_settings

# --- the eight step states ----------------------------------------------------------------

PLANNED = "planned"
WAITING_APPROVAL = "waiting_approval"
BLOCKED = "blocked"
EXECUTING = "executing"
COMPLETED_VERIFIED = "completed_verified"
COMPLETED_UNVERIFIED = "completed_unverified"
FAILED = "failed"
SKIPPED = "skipped"

STATES: frozenset[str] = frozenset(
    {
        PLANNED,
        WAITING_APPROVAL,
        BLOCKED,
        EXECUTING,
        COMPLETED_VERIFIED,
        COMPLETED_UNVERIFIED,
        FAILED,
        SKIPPED,
    }
)

# completed_verified, completed_unverified, skipped, and failed are terminal. failed is terminal
# except via correct_step (the named correction) or a future resume path.
TERMINAL_STATES: frozenset[str] = frozenset(
    {COMPLETED_VERIFIED, COMPLETED_UNVERIFIED, SKIPPED, FAILED}
)

# The single legal transition table every writer consults. There is no framework: a transition
# is legal exactly when the destination is in the source's set here.
TRANSITIONS: dict[str, frozenset[str]] = {
    PLANNED: frozenset({WAITING_APPROVAL, EXECUTING, BLOCKED, SKIPPED}),
    WAITING_APPROVAL: frozenset({PLANNED, EXECUTING, BLOCKED, SKIPPED}),
    BLOCKED: frozenset({PLANNED, WAITING_APPROVAL, EXECUTING, SKIPPED}),
    EXECUTING: frozenset({COMPLETED_VERIFIED, COMPLETED_UNVERIFIED, FAILED, BLOCKED}),
    COMPLETED_VERIFIED: frozenset(),
    COMPLETED_UNVERIFIED: frozenset(),
    FAILED: frozenset(),
    SKIPPED: frozenset(),
}

# Run roll up statuses. A run is active while any step is not terminal.
RUN_PLANNED = "planned"
RUN_EXECUTING = "executing"
RUN_WAITING_APPROVAL = "waiting_approval"
RUN_BLOCKED = "blocked"
RUN_FAILED = "failed"
RUN_COMPLETED = "completed"

ACTIVE_RUN_STATUSES: frozenset[str] = frozenset(
    {RUN_PLANNED, RUN_EXECUTING, RUN_WAITING_APPROVAL, RUN_BLOCKED}
)

# Inline evidence content larger than this is spilled to a file under the runtime root and kept
# in the row only by reference.
_INLINE_EVIDENCE_LIMIT = 4000
_PREVIEW_CHARS = 500


class RuntimeWriteError(Exception):
    """Raised when a writer is asked to author a field it does not own or make an illegal move."""


def transition_allowed(src: str, dst: str) -> bool:
    return dst in TRANSITIONS.get(src, frozenset())


# --- derivations (pure reads, never authorship) -------------------------------------------


def derive_run_status(steps: Sequence[AgentStep]) -> str:
    """Roll a run's step statuses up to a single cached run status. A pure function.

    Precedence reflects what most needs attention: a running step, then a gate, then a block,
    then unstarted work, then the terminal verdict. With no steps the run is planned.
    """
    statuses = {step.status for step in steps}
    if not statuses:
        return RUN_PLANNED
    if EXECUTING in statuses:
        return RUN_EXECUTING
    if WAITING_APPROVAL in statuses:
        return RUN_WAITING_APPROVAL
    if BLOCKED in statuses:
        return RUN_BLOCKED
    if PLANNED in statuses:
        return RUN_PLANNED
    # Every step is terminal. A single failure colours the whole run failed.
    if FAILED in statuses:
        return RUN_FAILED
    return RUN_COMPLETED


def _run_steps(db: Session, run: AgentRun) -> list[AgentStep]:
    return (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run.id)
        .order_by(AgentStep.seq.asc(), AgentStep.id.asc())
        .all()
    )


def _refresh_run_status(db: Session, run: AgentRun) -> None:
    """Recompute and persist the cached run status. This is a derivation sink, not authorship.

    Every writer calls it last so AgentRun.status always equals derive_run_status(steps).
    """
    run.status = derive_run_status(_run_steps(db, run))
    if run.status in (RUN_COMPLETED, RUN_FAILED):
        if run.finished_at is None:
            run.finished_at = utcnow()
    else:
        run.finished_at = None
    db.commit()
    db.refresh(run)


def _next_seq(db: Session, run: AgentRun) -> int:
    last = (
        db.query(AgentStep.seq)
        .filter(AgentStep.run_id == run.id)
        .order_by(AgentStep.seq.desc())
        .first()
    )
    return (last[0] + 1) if last else 1


# --- run creation (not step authorship) ---------------------------------------------------


def create_run(
    db: Session,
    *,
    project_id: int | None = None,
    autonomy_level: int = 0,
    plan: dict | None = None,
    goal_summary: str = "",
    context_summary: str = "",
    proposed_by: str = "user",
    kind: str = "general",
    branch_ref: str | None = None,
    parent_run_id: int | None = None,
    pm_run_id: int | None = None,
    schema_version: int = 1,
) -> AgentRun:
    """Insert a run header. A fresh run has no steps, so its derived status is planned."""
    run = AgentRun(
        project_id=project_id,
        autonomy_level=autonomy_level,
        plan=plan or {},
        goal_summary=goal_summary,
        context_summary=context_summary,
        proposed_by=proposed_by,
        kind=kind,
        branch_ref=branch_ref,
        parent_run_id=parent_run_id,
        pm_run_id=pm_run_id,
        schema_version=schema_version,
        status=RUN_PLANNED,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    _refresh_run_status(db, run)
    return run


# --- writer 1: propose_step (intent only, plus the entry gate) ----------------------------


def propose_step(
    db: Session,
    run: AgentRun,
    *,
    kind: str = "action",
    title: str = "",
    intent: str = "",
    payload: dict | None = None,
    proposed_by: str = "llm",
    idempotency_key: str | None = None,
) -> AgentStep:
    """Author a step's intent and place it at the entry gate.

    propose_step owns the entry edge and nothing else: it never sets an outcome, evidence, a
    tool_call, a failure, or an approval resolution; it has no parameters for them. The entry
    gate is deny-by-default. A step is created planned (auto-resolved past the gate) only when
    can_auto_resolve passes: a higher autonomy level and an explicit safe classification in the
    payload. Autonomy 0, an unclassified step, a missing safe tag, or any unsafe tag all leave
    the step waiting_approval for a human.

    idempotency_key is an intent-time identity the proposer may stamp on the unit of work so
    re-proposing it is idempotent. It is unique per run (enforced by the AgentStep index); a null
    key is the default and carries no uniqueness.
    """
    payload = payload or {}
    status = PLANNED if can_auto_resolve(payload, run.autonomy_level) else WAITING_APPROVAL
    step = AgentStep(
        run_id=run.id,
        seq=_next_seq(db, run),
        status=status,
        kind=kind,
        title=title[:300],
        intent=intent,
        payload=payload or {},
        proposed_by=proposed_by,
        idempotency_key=idempotency_key,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    _refresh_run_status(db, run)
    return step


# --- writer 2: record_execution (outcome, evidence, tool_call, failure) -------------------


def _spill_evidence(
    run_id: int, step_id: int, evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Move oversized inline evidence content to a file under the runtime root, by reference.

    An item with a large content string keeps its source and other keys, drops content, and
    gains content_ref (a path under NEXA_RUNTIME_ROOT), content_bytes, and a short preview.
    """
    settings = get_settings()
    out: list[dict[str, Any]] = []
    for index, item in enumerate(evidence):
        normalized = dict(item)
        content = normalized.get("content")
        if isinstance(content, str) and len(content) > _INLINE_EVIDENCE_LIMIT:
            relative = f"run_{run_id}/step_{step_id}_ev{index}.txt"
            safe_write_text(settings.nexa_runtime_root, relative, content)
            normalized.pop("content", None)
            normalized["content_ref"] = relative
            normalized["content_bytes"] = len(content.encode("utf-8"))
            normalized["content_preview"] = content[:_PREVIEW_CHARS]
        out.append(normalized)
    return out


def _has_tool_evidence(evidence: list[dict[str, Any]]) -> bool:
    return any(item.get("source") == "tool" for item in evidence)


def record_execution(
    db: Session,
    step: AgentStep,
    *,
    outcome: str,
    evidence: list[dict[str, Any]] | None = None,
    tool_call: dict[str, Any] | None = None,
    failure: dict[str, Any] | None = None,
) -> AgentStep:
    """Author what happened. The terminal status is derived, never accepted as a target.

    outcome is one of completed, failed, or blocked. A completed step becomes completed_verified
    when its evidence carries at least one tool sourced item, otherwise completed_unverified.
    completed_verified and completed_unverified are never passed in; only the work decides.
    A terminal step cannot be mutated here: that is correct_step's job.
    """
    if outcome not in ("completed", "failed", "blocked"):
        raise RuntimeWriteError(
            f"record_execution outcome must be completed, failed, or blocked, not {outcome!r}; "
            "verified is derived from evidence and is never a target"
        )
    if step.status in TERMINAL_STATES:
        raise RuntimeWriteError(
            f"record_execution cannot mutate a terminal step (status {step.status})"
        )

    items = list(evidence or [])

    # A step always runs through executing on its way to a terminal. Validate the entry hop,
    # unless the step is already executing.
    if step.status != EXECUTING and not transition_allowed(step.status, EXECUTING):
        raise RuntimeWriteError(f"illegal transition {step.status} -> {EXECUTING}")

    if outcome == "failed":
        target = FAILED
    elif outcome == "blocked":
        target = BLOCKED
    else:  # completed
        target = COMPLETED_VERIFIED if _has_tool_evidence(items) else COMPLETED_UNVERIFIED

    if not transition_allowed(EXECUTING, target):
        raise RuntimeWriteError(f"illegal transition {EXECUTING} -> {target}")

    step.evidence = _spill_evidence(step.run_id, step.id, items)
    step.tool_call = tool_call
    step.failure = failure
    step.outcome = "" if step.outcome is None else step.outcome
    step.status = target
    db.commit()
    db.refresh(step)

    run = db.get(AgentRun, step.run_id)
    if run is not None:
        _refresh_run_status(db, run)
    return step


# --- writer 3: resolve_approval (approval exit edges only) --------------------------------


def resolve_approval(
    db: Session,
    step: AgentStep,
    *,
    resolution: str,
    resolved_by: str = "user",
    note: str = "",
) -> AgentStep:
    """Resolve a gated step. Owns only the exit edges out of waiting_approval.

    approve moves waiting_approval -> planned, reject moves waiting_approval -> skipped. It
    writes only the approval payload and the status; never intent, outcome, or evidence.
    """
    if resolution not in ("approved", "rejected"):
        raise RuntimeWriteError("resolution must be approved or rejected")
    if step.status != WAITING_APPROVAL:
        raise RuntimeWriteError(
            f"resolve_approval requires a waiting_approval step, not {step.status}"
        )

    target = PLANNED if resolution == "approved" else SKIPPED
    if not transition_allowed(WAITING_APPROVAL, target):
        raise RuntimeWriteError(f"illegal transition {WAITING_APPROVAL} -> {target}")

    step.approval = {
        "resolution": resolution,
        "resolved_by": resolved_by,
        "note": note,
        "resolved_at": utcnow().isoformat(),
    }
    step.status = target
    db.commit()
    db.refresh(step)

    run = db.get(AgentRun, step.run_id)
    if run is not None:
        _refresh_run_status(db, run)
    return step


# --- writer 4: correct_step (terminal status corrections only) ----------------------------


def correct_step(
    db: Session,
    step: AgentStep,
    *,
    status: str,
    correction_note: str,
    corrected_by: str = "user",
) -> AgentStep:
    """Correct a terminal step's status, with an audit note. Changes status only.

    This is the only writer that may mutate a terminal state, and the only path out of failed
    besides a future resume. It records corrected_from and the note, and changes nothing about
    the step's intent or recorded outcome. completed_verified is derived and can never be set
    here.
    """
    if step.status not in TERMINAL_STATES:
        raise RuntimeWriteError(
            f"correct_step only corrects terminal steps, not {step.status}"
        )
    if status not in STATES:
        raise RuntimeWriteError(f"unknown target status {status!r}")
    if status == COMPLETED_VERIFIED:
        raise RuntimeWriteError(
            "completed_verified is derived from evidence and can never be set by correct_step"
        )
    if not correction_note.strip():
        raise RuntimeWriteError("correct_step requires a correction note")

    step.corrected_from = step.status
    step.correction_note = correction_note
    step.status = status
    db.commit()
    db.refresh(step)

    run = db.get(AgentRun, step.run_id)
    if run is not None:
        _refresh_run_status(db, run)
    return step
