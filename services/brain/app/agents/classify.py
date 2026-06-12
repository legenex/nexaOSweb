"""Classifier and decision record.

A captured item is classified into one of eight shapes. The shape determines the
recommended downstream route and the semantic model key that will handle it. The model
returns only a shape, a confidence, tags, and a plain reasoning summary. Routing and
model selection are deterministic in code, never delegated to the model. The reasoning
summary is the user readable explanation. There is no hidden chain of thought.
"""

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.json_extract import synthesize_json
from app.models.inbox import ClassificationRecord, InboxItem
from app.models.workspace import AppSetting
from app.router.model_router import ModelRouter, get_router
from app.settings import get_settings

logger = logging.getLogger(__name__)

SHAPES = [
    "project",
    "campaign",
    "technical",
    "gtd",
    "content",
    "private",
    "park",
    "archive",
]

# Shape to the workflow route consumed by the router.
SHAPE_ROUTES: dict[str, str] = {
    "project": "project",
    "campaign": "campaign",
    "technical": "technical",
    "gtd": "tasks",
    "content": "content",
    "private": "journal",
    "park": "park",
    "archive": "archive",
}

# Shape to the semantic model key that handles it downstream.
SHAPE_MODEL_KEYS: dict[str, str] = {
    "project": "agentic_code",
    "technical": "agentic_code",
    "campaign": "general",
    "content": "general",
    "gtd": "bulk",
    "private": "journal_reflection",
    "park": "bulk",
    "archive": "bulk",
}

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "shape": {"type": "string", "enum": SHAPES},
        "confidence": {"type": "number"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "reasoning_summary": {"type": "string"},
    },
    "required": ["shape", "confidence", "reasoning_summary"],
}


def _prompt(item: InboxItem) -> str:
    return (
        "Classify this captured item into exactly one shape and explain briefly.\n\n"
        f"Name: {item.name}\n"
        f"Body: {item.body}\n\n"
        "Shapes:\n"
        "- project: a multi step initiative that becomes a maintained project\n"
        "- campaign: a marketing or growth push\n"
        "- technical: a technical task or engineering investigation\n"
        "- gtd: a single actionable task to track\n"
        "- content: a piece of writing or media to produce\n"
        "- private: a personal note or reflection\n"
        "- park: not actionable now, revisit later\n"
        "- archive: reference only, no action\n\n"
        "Return shape, a confidence between 0 and 1, a few lowercase tags, and a one or "
        "two sentence reasoning_summary a person can read and challenge."
    )


def get_confidence_threshold(db: Session) -> float:
    setting = db.query(AppSetting).filter(AppSetting.key == "intake").first()
    if setting and isinstance(setting.value, dict):
        value = setting.value.get("confidence_threshold")
        if isinstance(value, int | float):
            return float(value)
    return get_settings().classify_confidence_threshold


def classify_item(
    db: Session,
    item: InboxItem,
    *,
    router: ModelRouter | None = None,
    synthesize: Callable[..., dict[str, Any]] | None = None,
) -> ClassificationRecord:
    """Classify an item, persist its decision record, and update the item status."""
    router = router or get_router()
    # Resolve the synthesizer at call time so the module global can be swapped in tests.
    synthesize = synthesize or synthesize_json
    result = synthesize("bulk", _prompt(item), _SCHEMA)

    shape = result.get("shape")
    if shape not in SHAPES:
        shape = "park"
    confidence = float(result.get("confidence", 0.0) or 0.0)
    confidence = max(0.0, min(1.0, confidence))
    tags = result.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    reasoning_summary = str(result.get("reasoning_summary", "")).strip()

    route = SHAPE_ROUTES[shape]
    model_key = SHAPE_MODEL_KEYS[shape]
    resolved_model_id = router.model_for(model_key)
    rationale = (
        f"A {shape} item is handled by the {model_key} model key, which resolves to "
        f"{resolved_model_id}."
    )

    record = ClassificationRecord(
        item_id=item.id,
        shape=shape,
        confidence=confidence,
        recommended_route=route,
        recommended_model_key=model_key,
        resolved_model_id=resolved_model_id,
        model_rationale=rationale,
        reasoning_summary=reasoning_summary,
        tags=tags,
    )
    db.add(record)

    threshold = get_confidence_threshold(db)
    item.status = "classified" if confidence >= threshold else "escalated"
    item.stage_history = [
        *item.stage_history,
        {"stage": "classify", "shape": shape, "confidence": confidence, "state": "done"},
    ]
    db.commit()
    db.refresh(record)
    return record


def classify_item_background(item_id: int) -> None:
    """Classify on ingest using a fresh session. Failures are swallowed and logged so a
    provider hiccup never breaks the capture request."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        item = db.get(InboxItem, item_id)
        if item is None:
            return
        already = (
            db.query(ClassificationRecord)
            .filter(ClassificationRecord.item_id == item_id)
            .first()
        )
        if already is not None:
            return
        classify_item(db, item)
        # Auto advance through Route unless the item was escalated.
        if item.status != "escalated":
            from app.agents.route import route_item

            route_item(db, item)
    except Exception:  # noqa: BLE001  background resilience
        logger.exception("background classification failed for item %s", item_id)
        db.rollback()
    finally:
        db.close()


def run_retry_sweep(db: Session, *, batch: int = 20) -> int:
    """Reclassify items that are still captured or escalated and lack a fresh decision.

    Returns the number of items processed. Used by the scheduled sweep.
    """
    pending = (
        db.query(InboxItem)
        .filter(InboxItem.status.in_(["captured", "escalated"]))
        .order_by(InboxItem.created_at.asc())
        .limit(batch)
        .all()
    )
    processed = 0
    for item in pending:
        try:
            classify_item(db, item)
            processed += 1
        except Exception:  # noqa: BLE001
            logger.exception("retry sweep failed for item %s", item.id)
            db.rollback()
    return processed
