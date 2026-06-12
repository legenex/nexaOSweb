"""Intake knobs: confidence threshold, classify sweep enabled, interval, batch.

Stored as an AppSetting row keyed "intake" per user, merged over the environment defaults.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.models.workspace import AppSetting
from app.schemas.settings import (
    IntakeSettings,
    IntakeSettingsPatch,
    KnowledgePolicy,
    KnowledgePolicyPatch,
)
from app.security.auth import current_user
from app.settings import get_settings

router = APIRouter(prefix="/settings", tags=["settings"])

INTAKE_KEY = "intake"
KNOWLEDGE_POLICY_KEY = "knowledge_policy"

# The human gate stays the default: ingestion off, approval required, connector memory off.
KNOWLEDGE_POLICY_DEFAULTS: dict = {
    "ingest_chatgpt_api": False,
    "ingest_claude_api": False,
    "ingest_connectors": False,
    "memory_require_approval": True,
    "memory_allow_dreaming": True,
    "memory_allow_connectors": False,
    "memory_min_confidence": 0.6,
}


def _defaults() -> dict:
    settings = get_settings()
    return {
        "confidence_threshold": settings.classify_confidence_threshold,
        "classify_sweep_enabled": settings.classify_sweep_enabled,
        "classify_sweep_interval": settings.classify_sweep_interval,
        "classify_batch": settings.classify_batch,
    }


def _row_for(db: Session, user: User, key: str) -> AppSetting | None:
    return (
        db.query(AppSetting)
        .filter(AppSetting.user_id == user.id, AppSetting.key == key)
        .first()
    )


def _merged(db: Session, user: User, key: str, defaults: dict) -> dict:
    values = dict(defaults)
    row = _row_for(db, user, key)
    if row and isinstance(row.value, dict):
        values.update({k: v for k, v in row.value.items() if k in values})
    return values


def _persist(db: Session, user: User, key: str, values: dict) -> None:
    row = _row_for(db, user, key)
    if row is None:
        db.add(AppSetting(user_id=user.id, key=key, value=values))
    else:
        row.value = values
    db.commit()


@router.get("", response_model=IntakeSettings)
def get_settings_endpoint(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> IntakeSettings:
    return IntakeSettings(**_merged(db, user, INTAKE_KEY, _defaults()))


@router.patch("", response_model=IntakeSettings)
def patch_settings(
    payload: IntakeSettingsPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> IntakeSettings:
    current = _merged(db, user, INTAKE_KEY, _defaults())
    current.update(payload.model_dump(exclude_none=True))
    _persist(db, user, INTAKE_KEY, current)
    return IntakeSettings(**current)


@router.get("/knowledge-policy", response_model=KnowledgePolicy)
def get_knowledge_policy(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> KnowledgePolicy:
    return KnowledgePolicy(**_merged(db, user, KNOWLEDGE_POLICY_KEY, KNOWLEDGE_POLICY_DEFAULTS))


@router.patch("/knowledge-policy", response_model=KnowledgePolicy)
def patch_knowledge_policy(
    payload: KnowledgePolicyPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> KnowledgePolicy:
    current = _merged(db, user, KNOWLEDGE_POLICY_KEY, KNOWLEDGE_POLICY_DEFAULTS)
    current.update(payload.model_dump(exclude_none=True))
    _persist(db, user, KNOWLEDGE_POLICY_KEY, current)
    return KnowledgePolicy(**current)
