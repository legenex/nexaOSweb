"""Flow stage endpoints: process and plan (extended by later prompts)."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.agents.builder import BuilderError, promote_project
from app.agents.clarify import apply_clarify, get_clarify, read_preview_html
from app.agents.process import ProcessError, process_item, read_plan_markdown
from app.db import get_db
from app.models.inbox import InboxItem
from app.models.project import Project
from app.models.user import User
from app.schemas.entities import ProjectRead
from app.schemas.flow import ClarifyRequest, ClarifyResponse, PromoteResponse
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


@router.get("/items/{item_id}/clarify", response_model=ClarifyResponse)
def clarify(
    item_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ClarifyResponse:
    item = load_owned_item(item_id, user, db)
    try:
        result = get_clarify(db, item)
    except ProcessError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ClarifyResponse(**result)


@router.post("/items/{item_id}/clarify", response_model=ProjectRead)
def submit_clarify(
    item_id: int,
    payload: ClarifyRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Project:
    item = load_owned_item(item_id, user, db)
    try:
        return apply_clarify(
            db,
            item,
            answers=payload.answers,
            selected_integration_ids=payload.selected_integration_ids,
            scope_changes=payload.scope_changes,
        )
    except ProcessError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/items/{item_id}/preview", response_class=HTMLResponse)
def get_preview(
    item_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    item = load_owned_item(item_id, user, db)
    project = db.query(Project).filter(Project.item_id == item.id).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no project for this item")
    try:
        return HTMLResponse(read_preview_html(project))
    except ProcessError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/items/{item_id}/promote", response_model=PromoteResponse)
def promote(
    item_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PromoteResponse:
    item = load_owned_item(item_id, user, db)
    project = db.query(Project).filter(Project.item_id == item.id).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no project for this item")
    if project.stage != "approved":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "project must be gate approved before promotion"
        )
    try:
        promoted, pm, requirements_path = promote_project(db, item, project)
    except BuilderError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return PromoteResponse(
        project_id=promoted.id,
        stage=promoted.stage,
        pm_run_id=pm.id,
        requirements_path=requirements_path,
    )
