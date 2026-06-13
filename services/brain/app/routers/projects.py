"""Projects listing and the human gate."""

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.inbox import InboxItem
from app.models.project import Project
from app.models.research import ProjectUpdate
from app.models.user import User
from app.schemas.entities import ProjectRead
from app.schemas.research import ProjectUpdateRead
from app.security.auth import current_user

router = APIRouter(prefix="/projects", tags=["projects"])


def _load_owned_project(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    if project.item_id is not None:
        item = db.get(InboxItem, project.item_id)
        if item is None or item.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[Project]:
    # Projects linked to the user's items, plus shared container projects (item_id null).
    owned_item_ids = [
        row.id for row in db.query(InboxItem.id).filter(InboxItem.user_id == user.id).all()
    ]
    return (
        db.query(Project)
        .filter((Project.item_id.in_(owned_item_ids)) | (Project.item_id.is_(None)))
        .order_by(Project.created_at.desc(), Project.id.desc())
        .all()
    )


@router.get("/{project_id}/updates", response_model=list[ProjectUpdateRead])
def list_updates(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ProjectUpdate]:
    # The project's Update Log, newest first. Research findings land here on a completed run.
    _load_owned_project(project_id, user, db)
    return (
        db.query(ProjectUpdate)
        .filter(ProjectUpdate.project_id == project_id)
        .order_by(ProjectUpdate.created_at.desc(), ProjectUpdate.id.desc())
        .all()
    )


@router.post("/{project_id}/approve", response_model=ProjectRead)
def approve(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Project:
    project = _load_owned_project(project_id, user, db)
    project.stage = "approved"
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/reject", response_model=ProjectRead)
def reject(
    project_id: int,
    reason: str = Body("", embed=True),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Project:
    project = _load_owned_project(project_id, user, db)
    project.stage = "rejected"
    plan = dict(project.plan_json or {})
    if reason:
        plan["rejection_reason"] = reason
        project.plan_json = plan
    db.commit()
    db.refresh(project)
    return project
