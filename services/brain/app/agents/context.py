"""Bounded agent context injection.

Assembles a compact system context for an agent run from the general model instructions, the
active Development and general knowledge, and the most recent rejected approaches and
corrections. The assembly is hard bounded to roughly MAX_CONTEXT_TOKENS: only active knowledge
is read, each item is summarised to a short snippet, sections are capped, and the whole context
is truncated so it never approaches the model budget or leaks the whole knowledge base. The
result is written to AgentRun.context_summary and returned.
"""

import logging

from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeEntry
from app.models.runtime import AgentRun, AgentStep
from app.models.workspace import AppSetting

logger = logging.getLogger(__name__)

# A deliberately conservative characters-per-token ratio for English, so the guard errs toward a
# smaller context than the true token count.
_CHARS_PER_TOKEN = 4
MAX_CONTEXT_TOKENS = 8000
_MAX_CHARS = MAX_CONTEXT_TOKENS * _CHARS_PER_TOKEN

# Per item and per section caps, so a single large entry cannot dominate and the base is never
# pulled in whole. Only active knowledge in these scopes is ever considered.
_SNIPPET_CHARS = 280
_INSTRUCTIONS_CHARS = 1500
_MAX_KNOWLEDGE = 40
_MAX_REJECTED = 10
_MAX_CORRECTIONS = 10
_CONTEXT_SCOPES = ("development", "general")


def estimate_tokens(text: str) -> int:
    """A rough token estimate from character length. Used by the guard and the test."""
    return (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN


def _summarise(text: str) -> str:
    flat = " ".join((text or "").split())
    return flat[:_SNIPPET_CHARS]


def _general_instructions(db: Session) -> str:
    row = (
        db.query(AppSetting)
        .filter(AppSetting.key == "general")
        .order_by(AppSetting.id.asc())
        .first()
    )
    if row and isinstance(row.value, dict):
        return str(row.value.get("general_instructions") or "").strip()
    return ""


def _active_knowledge(db: Session) -> list[KnowledgeEntry]:
    return (
        db.query(KnowledgeEntry)
        .filter(
            KnowledgeEntry.status == "active",
            KnowledgeEntry.scope.in_(_CONTEXT_SCOPES),
        )
        .order_by(KnowledgeEntry.confidence.desc(), KnowledgeEntry.updated_at.desc())
        .limit(_MAX_KNOWLEDGE)
        .all()
    )


def _recent_rejections(db: Session) -> list[AgentStep]:
    """Recent steps a human rejected at the gate, newest first. The note teaches what to avoid."""
    candidates = (
        db.query(AgentStep)
        .filter(AgentStep.approval.isnot(None))
        .order_by(AgentStep.updated_at.desc())
        .limit(_MAX_REJECTED * 5)
        .all()
    )
    out: list[AgentStep] = []
    for step in candidates:
        if isinstance(step.approval, dict) and step.approval.get("resolution") == "rejected":
            out.append(step)
        if len(out) >= _MAX_REJECTED:
            break
    return out


def _recent_corrections(db: Session) -> list[AgentStep]:
    return (
        db.query(AgentStep)
        .filter(AgentStep.correction_note.isnot(None))
        .order_by(AgentStep.updated_at.desc())
        .limit(_MAX_CORRECTIONS)
        .all()
    )


def assemble_context(db: Session) -> str:
    """Build the bounded context string. Never exceeds MAX_CONTEXT_TOKENS by estimate."""
    parts: list[str] = []
    used = 0

    def add(block: str) -> None:
        nonlocal used
        block = block.strip()
        if not block:
            return
        remaining = _MAX_CHARS - used - 2
        if remaining <= 0:
            return
        if len(block) > remaining:
            block = block[:remaining].rstrip()
        parts.append(block)
        used += len(block) + 2

    instructions = _general_instructions(db)
    if instructions:
        add("## Operating instructions\n" + instructions[:_INSTRUCTIONS_CHARS])

    entries = _active_knowledge(db)
    if entries:
        lines = [
            f"- ({e.scope}/{e.kind}, conf {e.confidence:.2f}) {_summarise(e.content)}"
            for e in entries
        ]
        add("## Active knowledge (development and general)\n" + "\n".join(lines))

    rejections = _recent_rejections(db)
    if rejections:
        lines = []
        for step in rejections:
            note = step.approval.get("note") if isinstance(step.approval, dict) else ""
            lines.append(f"- avoid: {_summarise(step.title)} ({_summarise(str(note or ''))})")
        add("## Recently rejected approaches (do not repeat)\n" + "\n".join(lines))

    corrections = _recent_corrections(db)
    if corrections:
        lines = [
            f"- correction: {_summarise(step.correction_note or '')} (was {step.corrected_from})"
            for step in corrections
        ]
        add("## Recent corrections\n" + "\n".join(lines))

    return "\n\n".join(parts)


def inject_context(db: Session, run: AgentRun) -> str:
    """Assemble the bounded context and write it to the run's context_summary."""
    summary = assemble_context(db)
    if estimate_tokens(summary) > MAX_CONTEXT_TOKENS:
        # Defensive belt: the assembler already bounds length, but never let an oversized
        # context reach a run. Truncate to the hard character ceiling.
        summary = summary[:_MAX_CHARS]
    run.context_summary = summary
    db.commit()
    db.refresh(run)
    return summary
