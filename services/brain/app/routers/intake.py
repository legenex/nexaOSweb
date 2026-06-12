"""Intake capture and item listing."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.inbox import InboxItem
from app.models.user import User
from app.safety import ensure_within_root
from app.schemas.entities import InboxItemRead
from app.schemas.intake import ItemsPage
from app.security.auth import current_user
from app.settings import get_settings
from app.util import safe_filename

router = APIRouter(prefix="/intake", tags=["intake"])


@router.post("/capture", response_model=InboxItemRead, status_code=status.HTTP_201_CREATED)
def capture(
    name: str = Form(...),
    body: str = Form(""),
    source: str = Form("note"),
    file: UploadFile | None = File(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> InboxItem:
    settings = get_settings()
    item = InboxItem(
        user_id=user.id,
        name=name.strip() or "Untitled",
        body=body,
        source=source,
        status="captured",
        stage_history=[{"stage": "capture", "state": "done"}],
    )
    db.add(item)
    db.flush()  # assign id before placing the upload

    if file is not None and file.filename:
        relative = Path("inbox") / str(item.id) / safe_filename(file.filename)
        target = ensure_within_root(settings.nexa_uploads_root, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            handle.write(file.file.read())
        item.stage_history = [
            *item.stage_history,
            {"stage": "capture", "file": str(relative), "source": source},
        ]

    db.commit()
    db.refresh(item)
    return item


@router.get("/items", response_model=ItemsPage)
def list_items(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ItemsPage:
    base = db.query(InboxItem).filter(InboxItem.user_id == user.id)
    total = base.with_entities(func.count(InboxItem.id)).scalar() or 0
    items = (
        base.order_by(InboxItem.created_at.desc(), InboxItem.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return ItemsPage(
        items=[InboxItemRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/items/{item_id}", response_model=InboxItemRead)
def get_item(
    item_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> InboxItem:
    item = db.get(InboxItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item not found")
    return item
