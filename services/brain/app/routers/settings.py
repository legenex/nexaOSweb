"""Intake knobs: confidence threshold, classify sweep enabled, interval, batch.

Stored as an AppSetting row keyed "intake" per user, merged over the environment defaults.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.models.workspace import AppSetting
from app.schemas.settings import IntakeSettings, IntakeSettingsPatch
from app.security.auth import current_user
from app.settings import get_settings

router = APIRouter(prefix="/settings", tags=["settings"])

INTAKE_KEY = "intake"


def _defaults() -> dict:
    settings = get_settings()
    return {
        "confidence_threshold": settings.classify_confidence_threshold,
        "classify_sweep_enabled": settings.classify_sweep_enabled,
        "classify_sweep_interval": settings.classify_sweep_interval,
        "classify_batch": settings.classify_batch,
    }


def _row_for(db: Session, user: User) -> AppSetting | None:
    return (
        db.query(AppSetting)
        .filter(AppSetting.user_id == user.id, AppSetting.key == INTAKE_KEY)
        .first()
    )


def _merged(db: Session, user: User) -> dict:
    values = _defaults()
    row = _row_for(db, user)
    if row and isinstance(row.value, dict):
        values.update({k: v for k, v in row.value.items() if k in values})
    return values


@router.get("", response_model=IntakeSettings)
def get_settings_endpoint(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> IntakeSettings:
    return IntakeSettings(**_merged(db, user))


@router.patch("", response_model=IntakeSettings)
def patch_settings(
    payload: IntakeSettingsPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> IntakeSettings:
    current = _merged(db, user)
    updates = payload.model_dump(exclude_none=True)
    current.update(updates)

    row = _row_for(db, user)
    if row is None:
        row = AppSetting(user_id=user.id, key=INTAKE_KEY, value=current)
        db.add(row)
    else:
        row.value = current
    db.commit()
    return IntakeSettings(**current)
