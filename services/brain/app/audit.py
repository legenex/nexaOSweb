"""The single write path into the agent governance audit log.

The build engine and the orchestrator never insert an AgentAudit row directly. They call
record_audit, or one of the thin event helpers below, so every audit row is validated, scoped, and
redaction checked the same way. The log is append-only at the ORM (see app/models/audit.py); this
module is the only place that adds to it.

Three invariants hold for every row:
  1. The (category, action) pair is one this module knows. An unknown pair is a programming error,
     raised, never silently logged.
  2. project_id is backfilled from the run when the caller passes only a run, so each row is self
     describing and the reads can scope by project with one column.
  3. No secret reaches a row. The reason and the structured detail are walked by the redaction guard
     (the same field name guard the backends apply to their transcripts) before insert.

Retention lives in AppSetting, not in a column, so it can change without a migration. The default is
keep all: nothing is ever pruned until an operator configures a window.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AgentAudit
from app.models.runtime import AgentRun
from app.models.workspace import AppSetting
from app.security.redaction import assert_no_secret

# --- actors -------------------------------------------------------------------------------

ACTOR_USER = "user"
ACTOR_SYSTEM = "system"
ACTOR_TYPES: frozenset[str] = frozenset({ACTOR_USER, ACTOR_SYSTEM})


def actor_type_for(actor: str | None) -> str:
    """Infer whether an actor identifier is the system or a user.

    The build engine resolves runs as "system:autonomy-green" and the orchestrator acts as
    "system"; everything else is a human (an email). Centralised here so every call site labels
    actors the same way.
    """
    return ACTOR_SYSTEM if (actor or "").strip().lower().startswith("system") else ACTOR_USER


# --- categories and the actions legal within each ------------------------------------------

CATEGORY_RUN = "run"
CATEGORY_BACKEND = "backend"
CATEGORY_GATE = "gate"
CATEGORY_APPROVAL = "approval"
CATEGORY_KILL_SWITCH = "kill_switch"
CATEGORY_ORCHESTRATOR = "orchestrator"

# The full set of governed events. record_audit refuses any pair not listed here, so a typo or an
# unmodelled event is caught at the call site rather than written as an orphan category.
CATEGORY_ACTIONS: dict[str, frozenset[str]] = {
    CATEGORY_RUN: frozenset({"run_start"}),
    CATEGORY_BACKEND: frozenset({"select"}),
    CATEGORY_GATE: frozenset({"decision"}),
    CATEGORY_APPROVAL: frozenset({"approve", "reject", "cancel"}),
    CATEGORY_KILL_SWITCH: frozenset({"engage", "release"}),
    CATEGORY_ORCHESTRATOR: frozenset({"pause", "resume"}),
}

# --- retention (AppSetting, no schema change to tune) --------------------------------------

AUDIT_RETENTION_KEY = "agent_audit_retention"
# keep_all means never prune. max_days is the window when mode becomes prune_after_days later.
AUDIT_RETENTION_DEFAULTS: dict[str, Any] = {"mode": "keep_all", "max_days": None}


class AuditError(Exception):
    """Raised for an unknown category, an illegal action, or an unknown actor type."""


def audit_retention(db: Session) -> dict[str, Any]:
    """The effective retention policy, the keep all default merged with any stored override.

    Stored as a single global AppSetting row (user_id null), because retention is a system policy,
    not a per user preference. Reading defaults when absent mirrors the settings router pattern.
    """
    values = dict(AUDIT_RETENTION_DEFAULTS)
    row = (
        db.query(AppSetting)
        .filter(AppSetting.user_id.is_(None), AppSetting.key == AUDIT_RETENTION_KEY)
        .first()
    )
    if row and isinstance(row.value, dict):
        values.update({k: v for k, v in row.value.items() if k in values})
    return values


def record_audit(
    db: Session,
    *,
    category: str,
    action: str,
    actor: str,
    actor_type: str = ACTOR_SYSTEM,
    reason: str = "",
    project_id: int | None = None,
    run_id: int | None = None,
    step_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> AgentAudit:
    """Append one governance event. The only insert path into the audit log.

    Validates the (category, action) pair and the actor type, backfills project_id from the run,
    runs the redaction guard over the reason and detail, then inserts. Never updates an existing
    row: the log is append-only.
    """
    if category not in CATEGORY_ACTIONS:
        raise AuditError(f"unknown audit category {category!r}")
    if action not in CATEGORY_ACTIONS[category]:
        raise AuditError(f"action {action!r} is not legal for audit category {category!r}")
    if actor_type not in ACTOR_TYPES:
        raise AuditError(f"actor_type must be user or system, not {actor_type!r}")

    detail = dict(detail or {})

    if project_id is None and run_id is not None:
        run = db.get(AgentRun, run_id)
        if run is not None:
            project_id = run.project_id

    # The redaction backstop: a secret bearing field name in the reason or detail is refused before
    # it can be persisted. The same guard the backends apply, reused here so secrets stay server
    # side and never leak into a durable, exportable governance row.
    assert_no_secret({"reason": reason, "detail": detail}, where="audit row")

    row = AgentAudit(
        category=category,
        action=action,
        actor_type=actor_type,
        actor=actor or ACTOR_SYSTEM,
        reason=reason or "",
        project_id=project_id,
        run_id=run_id,
        step_id=step_id,
        detail=detail,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --- thin event helpers -------------------------------------------------------------------
# Each encodes the category, action, and detail shape of one governed event so producers express
# intent rather than wiring strings, and the payload schema for an event lives in one place.


def audit_run_start(
    db: Session,
    run: AgentRun,
    *,
    actor: str,
    actor_type: str | None = None,
    reason: str = "",
    detail: dict[str, Any] | None = None,
) -> AgentAudit:
    """A run was started, by a user or the system."""
    return record_audit(
        db,
        category=CATEGORY_RUN,
        action="run_start",
        actor=actor,
        actor_type=actor_type or actor_type_for(actor),
        reason=reason,
        run_id=run.id,
        project_id=run.project_id,
        detail=detail,
    )


def audit_backend_selection(
    db: Session,
    *,
    trail: dict[str, Any],
    run: AgentRun | None = None,
    project_id: int | None = None,
    actor: str = ACTOR_SYSTEM,
    reason: str = "",
) -> AgentAudit:
    """The backend selection trail: which backends were considered and which won, and why.

    The trail carries the full BackendChoice projection (the chosen backend, the policy source, the
    ordered candidates, and the per candidate verdict, including any skipped over its cost ceiling),
    so the choice and every skip is auditable from one row.
    """
    return record_audit(
        db,
        category=CATEGORY_BACKEND,
        action="select",
        actor=actor,
        actor_type=actor_type_for(actor),
        reason=reason,
        run_id=run.id if run is not None else None,
        project_id=project_id if run is None else run.project_id,
        detail={"trail": trail},
    )


def audit_gate_decision(
    db: Session,
    *,
    run: AgentRun,
    effective_level: int | str,
    categories: list[str],
    reasons: list[str],
    step_id: int | None = None,
    actor: str = ACTOR_SYSTEM,
    reason: str = "",
) -> AgentAudit:
    """A gate decision: the effective autonomy level, the risk categories, and the reasons."""
    return record_audit(
        db,
        category=CATEGORY_GATE,
        action="decision",
        actor=actor,
        actor_type=actor_type_for(actor),
        reason=reason or "; ".join(reasons),
        run_id=run.id,
        step_id=step_id,
        detail={
            "effective_level": effective_level,
            "categories": list(categories),
            "reasons": list(reasons),
        },
    )


def audit_approval(
    db: Session,
    *,
    action: str,
    actor: str,
    reason: str = "",
    run: AgentRun | None = None,
    run_id: int | None = None,
    step_id: int | None = None,
) -> AgentAudit:
    """An approve, reject, or cancel against a gated step or a run."""
    return record_audit(
        db,
        category=CATEGORY_APPROVAL,
        action=action,
        actor=actor,
        actor_type=actor_type_for(actor),
        reason=reason,
        run_id=run.id if run is not None else run_id,
        step_id=step_id,
    )


def audit_kill_switch(
    db: Session,
    *,
    action: str,
    actor: str,
    reason: str = "",
    project_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> AgentAudit:
    """A kill switch engage or release."""
    return record_audit(
        db,
        category=CATEGORY_KILL_SWITCH,
        action=action,
        actor=actor,
        actor_type=actor_type_for(actor),
        reason=reason,
        project_id=project_id,
        detail=detail,
    )


def audit_orchestrator(
    db: Session,
    *,
    action: str,
    actor: str = ACTOR_SYSTEM,
    reason: str = "",
    project_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> AgentAudit:
    """An orchestrator pause or resume."""
    return record_audit(
        db,
        category=CATEGORY_ORCHESTRATOR,
        action=action,
        actor=actor,
        actor_type=actor_type_for(actor),
        reason=reason,
        project_id=project_id,
        detail=detail,
    )
