"""Agent runtime spine: AgentRun and AgentStep.

The runtime records what an agent intended, did, and proved, as durable truth. It is the
ledger the executor will later drive, but the ledger itself is authored only through the four
writers in app/runtime.py, each owning a disjoint slice of a step's fields. Nothing here lets
a caller assert a verified outcome: completed_verified is derived from tool sourced evidence,
never written as a target.

Two tables only. AgentRun is the per run header with the plan and summaries. AgentStep is the
ordered ledger of steps, each carrying intent (authored by propose_step), outcome and evidence
(authored by record_execution), an approval resolution (authored by resolve_approval), and
terminal corrections (authored by correct_step). Large tool output is stored by reference under
NEXA_RUNTIME_ROOT rather than inline.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, utcnow


class AgentRun(Base, TimestampMixin):
    """The header for one agent run: its plan, summaries, and a derived cached status.

    The status column is a pure derivation of the run's step statuses, refreshed by every
    writer. branch_ref and cursor_step_id are seams for the future executor and resume path and
    carry no logic here. parent_run_id and pm_run_id are nullable seams for multi run handoff
    and the project manager link.
    """

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=True
    )
    # Cached roll up of the step statuses. Always equal to derive_run_status(steps).
    status: Mapped[str] = mapped_column(String(40), default="planned", index=True, nullable=False)
    # The full autonomy range 0 to 4 is stored and no writer clamps it. Only the binary is
    # honored now: 0 gates every step at waiting_approval, non-zero does not force the gate.
    # The prompt 8 safe set check will refine the non-zero behaviour later.
    autonomy_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # The branch or workspace the executor will run on. A nullable seam with no logic here.
    branch_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # The resume cursor: the step the next resume would continue after. Enforced in the app and
    # router, not at the database level, to avoid a circular foreign key with agent_steps.
    cursor_step_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The ordered plan payload the run was created from.
    plan: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    goal_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    context_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Who proposed the run: user, llm, or system.
    proposed_by: Mapped[str] = mapped_column(String(40), default="user", nullable=False)
    # Nullable seams. parent_run_id supports multi run handoff; pm_run_id links a project
    # manager run. Neither carries logic in the runtime core.
    parent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id"), index=True, nullable=True
    )
    pm_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("pm_runs.id"), index=True, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentStep(Base, TimestampMixin):
    """One step in a run's ledger. Its fields are partitioned across the four writers.

    Intent (kind, title, intent, payload, proposed_by) is authored only by propose_step.
    Outcome (outcome, evidence, tool_call, failure) is authored only by record_execution.
    The approval resolution is authored only by resolve_approval. Terminal corrections
    (correction_note, corrected_from, and the status change) are authored only by correct_step.
    status moves only along the legal transition table; completed_verified is derived from
    tool sourced evidence and is never written as a target.
    """

    __tablename__ = "agent_steps"
    __table_args__ = (Index("ix_agent_steps_run_id_seq", "run_id", "seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id"), index=True, nullable=False
    )
    # Monotonic order within the run, assigned by propose_step.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # One of the eight runtime states. See app/runtime.py STATES.
    status: Mapped[str] = mapped_column(String(40), default="planned", index=True, nullable=False)

    # --- intent, authored by propose_step ---
    kind: Mapped[str] = mapped_column(String(40), default="action", nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    intent: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    proposed_by: Mapped[str] = mapped_column(String(40), default="llm", nullable=False)

    # --- outcome, authored by record_execution ---
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A list of evidence items, each {source: tool|llm|user, ...}. A tool sourced item is what
    # makes a completed step verified. Large outputs are stored by reference under the runtime
    # root and represented here with a content_ref plus a byte count and a short preview.
    evidence: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tool_call: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    failure: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # --- approval resolution, authored by resolve_approval ---
    approval: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # --- terminal correction, authored by correct_step ---
    correction_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_from: Mapped[str | None] = mapped_column(String(40), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
