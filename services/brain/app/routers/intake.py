"""Intake capture and item listing."""

from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agents.classify import classify_item_background
from app.db import get_db
from app.json_extract import synthesize_json
from app.models.inbox import ClassificationRecord, InboxItem
from app.models.user import User
from app.safety import ensure_within_root
from app.schemas.entities import ClassificationRecordRead, InboxItemRead
from app.schemas.intake import ExpandRequest, ExpandResponse, ItemsPage
from app.security.auth import current_user
from app.settings import get_settings
from app.util import safe_filename

router = APIRouter(prefix="/intake", tags=["intake"])


@router.post("/capture", response_model=InboxItemRead, status_code=status.HTTP_201_CREATED)
def capture(
    background_tasks: BackgroundTasks,
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

    # Classify on ingest, in the background, so capture stays fast and resilient.
    background_tasks.add_task(classify_item_background, item.id)
    return item


@router.post("/expand", response_model=ExpandResponse)
def expand(
    payload: ExpandRequest,
    _user: User = Depends(current_user),
) -> ExpandResponse:
    """Enrich a short capture into a fuller description. Used by Generate with AI."""
    prompt = (
        "Expand this rough capture into a clear, concrete description of two or three "
        "sentences for a US market product. Return JSON with an expanded field.\n\n"
        f"Name: {payload.name}\nNotes: {payload.body}"
    )
    schema = {
        "type": "object",
        "properties": {"expanded": {"type": "string"}},
        "required": ["expanded"],
    }
    result = synthesize_json("general", prompt, schema)
    return ExpandResponse(expanded=str(result.get("expanded", "")).strip())


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


@router.get("/items/{item_id}/classification", response_model=ClassificationRecordRead)
def get_classification(
    item_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ClassificationRecord:
    item = db.get(InboxItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item not found")
    record = (
        db.query(ClassificationRecord)
        .filter(ClassificationRecord.item_id == item_id)
        .order_by(ClassificationRecord.created_at.desc(), ClassificationRecord.id.desc())
        .first()
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no classification yet")
    return record
