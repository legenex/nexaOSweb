"""Agent governance audit: the append-only AgentAudit ledger.

Every governed moment of the build engine writes one immutable row here: a run start, the
backend selection trail, a gate decision (with its effective level, categories, and reasons),
each approve, reject, and cancel, each kill switch engage and release, and each orchestrator
pause and resume. Every row names an actor (a user or the system), a reason, and a timestamp.

The table is append-only by construction. Two mapper listeners refuse any UPDATE or DELETE on an
AgentAudit row, so a written event can never be altered or hard deleted, only added to. project_id
and run_id are plain indexed columns with no database level foreign key (like Task.run_id), so the
log is never blocked or cascaded by the state of the rows it describes; the scoping relationship is
enforced in the router. Secrets never reach a row: the writer in app/audit.py runs the redaction
guard before insert.
"""

from sqlalchemy import JSON, Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AuditAppendOnlyError(Exception):
    """Raised when an AgentAudit row would be updated or deleted. The log is append-only."""


class AgentAudit(Base, TimestampMixin):
    """One immutable governance event. created_at (from TimestampMixin) is the event timestamp."""

    __tablename__ = "agent_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The high level event grouping the audit reads filter on (run, backend, gate, approval,
    # kill_switch, orchestrator). Validated against CATEGORY_ACTIONS in app/audit.py.
    category: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    # The specific event within the category (for example run_start, select, decision, approve).
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    # Who acted: user or system. The actor column carries the identifier (an email, or "system").
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    # The human readable reason for the event. Never carries a secret (see the redaction guard).
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # The run and project the event belongs to, backfilled from the run when known. Plain indexed
    # columns, no database level foreign key, so the log is independent of the rows it describes.
    project_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    run_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # The step a gate or approval event resolved, when the event is about one step.
    step_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The structured event payload: the backend selection trail, the gate decision fields, and so
    # on. Passed through the redaction guard before insert so no secret bearing field lands here.
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


@event.listens_for(AgentAudit, "before_update", propagate=True)
def _block_update(_mapper, _connection, _target) -> None:
    raise AuditAppendOnlyError("agent_audit is append-only; an audit row may never be updated")


@event.listens_for(AgentAudit, "before_delete", propagate=True)
def _block_delete(_mapper, _connection, _target) -> None:
    raise AuditAppendOnlyError("agent_audit is append-only; an audit row may never be deleted")
