"""Flow stage endpoints: process and plan (extended by later prompts)."""

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.agents.builder import BuilderError, promote_project
from app.agents.clarify import apply_clarify, get_clarify, read_preview_html
from app.agents.process import ProcessError, process_item, read_plan_markdown
from app.agents.readiness import (
    evaluate_readiness,
    latest_readiness_run,
    readiness_assessment,
)
from app.aggregate import build_flow_item
from app.db import get_db
from app.models.inbox import InboxItem
from app.models.project import Project
from app.models.user import User
from app.safety import ensure_within_root
from app.schemas.entities import ProjectRead
from app.schemas.flow import (
    ClarifyRequest,
    ClarifyResponse,
    FlowItemDTO,
    PromoteResponse,
    ReadinessAssessment,
)
from app.security.auth import current_user
from app.settings import get_settings

router = APIRouter(prefix="/flow", tags=["flow"])


def load_owned_item(item_id: int, user: User, db: Session) -> InboxItem:
    item = db.get(InboxItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item not found")
    return item


@router.get("/items", response_model=list[FlowItemDTO])
def list_flow_items(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[FlowItemDTO]:
    items = (
        db.query(InboxItem)
        .filter(InboxItem.user_id == user.id)
        .order_by(InboxItem.created_at.desc(), InboxItem.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [build_flow_item(db, item) for item in items]


@router.get("/items/{item_id}", response_model=FlowItemDTO)
def get_flow_item(
    item_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> FlowItemDTO:
    item = load_owned_item(item_id, user, db)
    return build_flow_item(db, item)


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


def _owned_project(item_id: int, user: User, db: Session) -> Project:
    """The project for an item the user owns, or a 404 if either is missing."""
    item = load_owned_item(item_id, user, db)
    project = db.query(Project).filter(Project.item_id == item.id).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no project for this item")
    return project


@router.get("/items/{item_id}/archive")
def download_project_archive(
    item_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Stream the project's on disk folder as a zip the browser can download.

    Zips every file under NEXA_PROJECTS_ROOT/<slug> through the path safety gate, so the user
    gets the real project directory (project_plan.md and the rest, unzipping under a <slug>
    folder). Returns 404 when the project has not been processed yet and the folder is absent.
    """
    project = _owned_project(item_id, user, db)
    settings = get_settings()
    folder = ensure_within_root(settings.nexa_projects_root, project.slug)
    if not folder.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no project folder yet")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                arcname = (Path(project.slug) / path.relative_to(folder)).as_posix()
                archive.write(path, arcname=arcname)
    buffer.seek(0)

    filename = f"nexa-{project.slug}.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _readiness_plan(project: Project) -> dict:
    """Build the plan the readiness service reads from what the project already holds.

    The draft plan_json carries the answers and any declared requirements; the chosen
    integrations (falling back to the plan's likely list) become the credential items.
    """
    plan = dict(project.plan_json or {})
    integrations = [str(value) for value in (project.selected_integrations or [])]
    if not integrations:
        likely = plan.get("likely_integrations")
        if isinstance(likely, list):
            integrations = [str(value) for value in likely]
    plan["selected_integrations"] = integrations
    return plan


@router.post("/items/{item_id}/readiness", response_model=ReadinessAssessment)
def evaluate_item_readiness(
    item_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Run the readiness assessment for this item's project at the Human Gate.

    Answers every item it can from the knowledge sources before asking the user; blocking gaps land
    in the existing approval queue and credential gaps in the secure provide path. A secret is never
    written here. Returns the fresh assessment.
    """
    project = _owned_project(item_id, user, db)
    plan = _readiness_plan(project)
    run = evaluate_readiness(db, plan=plan, project_id=project.id, user_id=user.id)
    return readiness_assessment(db, run)


@router.get("/items/{item_id}/readiness", response_model=ReadinessAssessment)
def get_item_readiness(
    item_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """The latest readiness assessment for this item's project.

    When the project has never been assessed, return an unassessed result (run_id 0, not
    satisfied, no items) rather than a 404. The gate stays closed because satisfied is false, and
    the panel shows an honest not yet assessed state without a console error.
    """
    project = _owned_project(item_id, user, db)
    run = latest_readiness_run(db, project.id)
    if run is None:
        return {
            "run_id": 0,
            "project_id": project.id,
            "kind": "readiness",
            "satisfied": False,
            "items": [],
            "blocking_open": [],
        }
    return readiness_assessment(db, run)
