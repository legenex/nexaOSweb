"""Dashboard endpoints: the Command Radar summary and the cached time aware brief.

The summary is read only aggregation. The brief is generated through the model router and
cached per day and per mode in an AppSetting row, so opening the Dashboard does not
regenerate it. A refresh query forces regeneration.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.dashboard import build_brief, build_summary
from app.db import get_db
from app.models.user import User
from app.models.workspace import AppSetting
from app.schemas.dashboard import BriefMode, DashboardBrief, DashboardSummary
from app.security.auth import current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

BRIEF_CACHE_KEY = "dashboard_brief"

# Before this hour the brief sets the day; from it on, it reviews and sets tomorrow.
EVENING_HOUR = 17


def _default_mode(now: datetime) -> BriefMode:
    return "evening" if now.hour >= EVENING_HOUR else "morning"


def _cache_row(db: Session, user: User) -> AppSetting | None:
    return (
        db.query(AppSetting)
        .filter(AppSetting.user_id == user.id, AppSetting.key == BRIEF_CACHE_KEY)
        .first()
    )


@router.get("/summary", response_model=DashboardSummary)
def get_summary(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> DashboardSummary:
    return build_summary(db, user, version=request.app.version)


@router.get("/brief", response_model=DashboardBrief)
def get_brief(
    mode: BriefMode | None = Query(default=None),
    refresh: bool = Query(default=False),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> DashboardBrief:
    now = datetime.now().astimezone()
    resolved_mode: BriefMode = mode or _default_mode(now)
    today = now.date().isoformat()

    row = _cache_row(db, user)
    cache: dict = dict(row.value) if row and isinstance(row.value, dict) else {}
    entry = cache.get(resolved_mode)

    if not refresh and isinstance(entry, dict) and entry.get("date") == today:
        return DashboardBrief(
            mode=resolved_mode,
            date=today,
            generated_at=entry["generated_at"],
            cached=True,
            text=entry["text"],
        )

    text = build_brief(db, user, resolved_mode, today=today)
    generated_at = now.isoformat()
    cache[resolved_mode] = {"date": today, "text": text, "generated_at": generated_at}

    if row is None:
        db.add(AppSetting(user_id=user.id, key=BRIEF_CACHE_KEY, value=cache))
    else:
        row.value = cache
    db.commit()

    return DashboardBrief(
        mode=resolved_mode,
        date=today,
        generated_at=generated_at,
        cached=False,
        text=text,
    )
