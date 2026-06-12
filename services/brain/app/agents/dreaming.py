"""Nightly Dreaming consolidation.

Reads the day's signals (journal notes, captured ideas, project activity) and asks the cheap
bulk model to extract one memory candidate per signal, about the user or about the system
itself. Candidates land in the review queue as pending. Nothing reaches the Knowledge base
until a candidate is explicitly accepted. Input is capped to the day's items.
"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.json_extract import synthesize_json
from app.models.base import utcnow
from app.models.dreaming import DreamRun, MemoryCandidate
from app.models.inbox import InboxItem
from app.models.project import Project
from app.models.workspace import JournalNote
from app.settings import get_settings

logger = logging.getLogger(__name__)

# Extraction and summarisation run on the cheap bulk key. Swapping the model is a one line
# change in config/models.yaml. The dedicated dreaming key is reserved there for the job.
EXTRACTION_MODEL_KEY = "bulk"

FACETS = ["about_user", "about_self"]
KINDS = ["fact", "preference", "pattern", "skill", "rule"]
SCOPES = ["general", "personal", "development", "work"]

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "facet": {"type": "string", "enum": FACETS},
        "kind": {"type": "string", "enum": KINDS},
        "scope": {"type": "string", "enum": SCOPES},
        "content": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["facet", "kind", "scope", "content", "confidence"],
}

Signal = dict[str, Any]
Synthesizer = Callable[..., dict[str, Any]]


def _gather_signals(db: Session, *, since: datetime, limit: int) -> list[Signal]:
    """Collect the day's signals from journal notes, captured ideas, and project activity."""
    signals: list[tuple[datetime, Signal]] = []

    for note in db.query(JournalNote).filter(JournalNote.created_at >= since).all():
        body = note.body or ""
        title = body.strip().splitlines()[0][:60] if body.strip() else f"journal {note.id}"
        signals.append(
            (
                note.created_at,
                {"ref_type": "journal", "ref_id": note.id, "title": title, "text": body},
            )
        )

    for item in db.query(InboxItem).filter(InboxItem.created_at >= since).all():
        signals.append(
            (
                item.created_at,
                {
                    "ref_type": "inbox",
                    "ref_id": item.id,
                    "title": item.name,
                    "text": item.body or "",
                },
            )
        )

    for project in db.query(Project).filter(Project.created_at >= since).all():
        signals.append(
            (
                project.created_at,
                {
                    "ref_type": "project",
                    "ref_id": project.id,
                    "title": project.name,
                    "text": f"Project {project.name} is at stage {project.stage}.",
                },
            )
        )

    signals.sort(key=lambda pair: pair[0], reverse=True)
    return [signal for _, signal in signals[:limit]]


def _prompt(signal: Signal) -> str:
    return (
        "Extract a single durable memory candidate from this signal. Decide whether it is "
        "about_user (a fact, preference, or pattern about the person) or about_self "
        "(something the system learned about its own operation).\n\n"
        f"Name: {signal['title']}\n"
        f"Notes: {signal['text'][:600]}\n\n"
        "Return facet, kind (one of fact, preference, pattern, skill, rule), scope (one of "
        "general, personal, development, work), a one sentence content statement, and a "
        "confidence between 0 and 1."
    )


def _coerce(result: dict[str, Any], signal: Signal) -> tuple[str, str, str, str, float]:
    facet = result.get("facet")
    if facet not in FACETS:
        facet = "about_user"
    kind = result.get("kind")
    if kind not in KINDS:
        kind = "fact"
    scope = result.get("scope")
    if scope not in SCOPES:
        scope = "general"
    content = str(result.get("content", "")).strip()
    if not content:
        content = f"Observed from {signal['ref_type']}: {signal['title']}"
    confidence = max(0.0, min(1.0, float(result.get("confidence", 0.5) or 0.5)))
    return facet, kind, scope, content, confidence


def run_dream(
    db: Session,
    *,
    trigger: str = "manual",
    synthesize: Synthesizer | None = None,
    now: datetime | None = None,
    lookback_hours: int | None = None,
    max_items: int | None = None,
) -> DreamRun:
    """Run one consolidation pass and return the DreamRun history record."""
    settings = get_settings()
    synthesize = synthesize or synthesize_json
    now = now or utcnow()
    lookback = lookback_hours if lookback_hours is not None else settings.dreaming_lookback_hours
    cap = max_items if max_items is not None else settings.dreaming_max_items
    since = now - timedelta(hours=lookback)

    run = DreamRun(status="running", trigger=trigger, model_key=EXTRACTION_MODEL_KEY)
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        signals = _gather_signals(db, since=since, limit=cap)
        created = 0
        for signal in signals:
            try:
                result = synthesize(EXTRACTION_MODEL_KEY, _prompt(signal), _SCHEMA)
            except Exception:  # noqa: BLE001  one bad signal must not fail the run
                logger.exception(
                    "dream extraction failed for %s %s", signal["ref_type"], signal["ref_id"]
                )
                continue
            facet, kind, scope, content, confidence = _coerce(result, signal)
            source_ref = {
                "type": signal["ref_type"],
                "id": signal["ref_id"],
                "title": signal["title"],
            }
            db.add(
                MemoryCandidate(
                    facet=facet,
                    kind=kind,
                    scope=scope,
                    content=content,
                    confidence=confidence,
                    source_refs=[source_ref],
                    status="pending",
                )
            )
            created += 1

        run.items_considered = len(signals)
        run.candidates_created = created
        run.status = "completed"
        run.finished_at = utcnow()
        db.commit()
        db.refresh(run)
        return run
    except Exception:
        db.rollback()
        run.status = "failed"
        run.finished_at = utcnow()
        db.commit()
        raise
