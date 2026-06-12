"""Flow stage endpoints: process and plan (extended by later prompts)."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.agents.process import ProcessError, process_item, read_plan_markdown
from app.db import get_db
from app.models.inbox import InboxItem
from app.models.project import Project
from app.models.user import User
from app.schemas.entities import ProjectRead
from app.security.auth import current_user

router = APIRouter(prefix="/flow", tags=["flow"])


def load_owned_item(item_id: int, user: User, db: Session) -> InboxItem:
    item = db.get(InboxItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item not found")
    return item


@router.post("/items/{item_id}/process", response_model=ProjectRead)
def process(
    item_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Project:
    item = load_owned_item(item_id, user, db)
    try:
        return process_item(db, item)
    except ProcessError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/items/{item_id}/plan", response_class=PlainTextResponse)
def get_plan(
    item_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    item = load_owned_item(item_id, user, db)
    project = db.query(Project).filter(Project.item_id == item.id).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no project for this item")
    try:
        content = read_plan_markdown(project)
    except ProcessError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return PlainTextResponse(content, media_type="text/markdown")
