"""Research to project link, runs, and finding level actions.

A research project attaches to a build project, runs produce findings, and each finding can
become a task, a project update, or a saved knowledge entry. Attaching a run target makes a
completed run post its findings into the build project's Update Log.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.agents.research import run_research
from app.db import get_db
from app.models.knowledge import KnowledgeEntry
from app.models.project import Project
from app.models.research import ProjectUpdate, ResearchFinding, ResearchRun
from app.models.user import User
from app.models.workspace import Task
from app.schemas.entities import ProjectRead, TaskRead
from app.schemas.knowledge import KnowledgeEntryRead
from app.schemas.research import (
    AttachRequest,
    ProjectUpdateRead,
    ResearchFindingRead,
    ResearchRunRead,
)
from app.security.auth import current_user

router = APIRouter(prefix="/research", tags=["research"])


def _load_project(project_id: int, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "project not found")
    return project


def _load_finding(finding_id: int, db: Session) -> ResearchFinding:
    finding = db.get(ResearchFinding, finding_id)
    if finding is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "finding not found")
    return finding


@router.post("/{research_id}/attach", response_model=ProjectRead)
def attach(
    research_id: int,
    payload: AttachRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Project:
    research = _load_project(research_id, db)
    if payload.target_project_id == research_id:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST, "a research project cannot attach to itself"
        )
    _load_project(payload.target_project_id, db)  # the build project must exist
    research.research_target_id = payload.target_project_id
    db.commit()
    db.refresh(research)
    return research


@router.post("/{research_id}/detach", response_model=ProjectRead)
def detach(
    research_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Project:
    research = _load_project(research_id, db)
    research.research_target_id = None
    db.commit()
    db.refresh(research)
    return research


@router.post(
    "/{research_id}/runs",
    response_model=ResearchRunRead,
    status_code=http_status.HTTP_201_CREATED,
)
def trigger_run(
    research_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ResearchRun:
    research = _load_project(research_id, db)
    run = run_research(db, research)
    # Attach the run's findings as a transient attribute for the response.
    run.findings = (
        db.query(ResearchFinding)
        .filter(ResearchFinding.run_id == run.id)
        .order_by(ResearchFinding.id.asc())
        .all()
    )
    return run


@router.get("/{research_id}/runs", response_model=list[ResearchRunRead])
def list_runs(
    research_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ResearchRun]:
    _load_project(research_id, db)
    runs = (
        db.query(ResearchRun)
        .filter(ResearchRun.project_id == research_id)
        .order_by(ResearchRun.created_at.desc(), ResearchRun.id.desc())
        .all()
    )
    for run in runs:
        run.findings = (
            db.query(ResearchFinding)
            .filter(ResearchFinding.run_id == run.id)
            .order_by(ResearchFinding.id.asc())
            .all()
        )
    return runs


@router.get("/{research_id}/findings", response_model=list[ResearchFindingRead])
def list_findings(
    research_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ResearchFinding]:
    _load_project(research_id, db)
    return (
        db.query(ResearchFinding)
        .filter(ResearchFinding.project_id == research_id)
        .order_by(ResearchFinding.created_at.desc(), ResearchFinding.id.desc())
        .all()
    )


@router.post(
    "/findings/{finding_id}/to-task",
    response_model=TaskRead,
    status_code=http_status.HTTP_201_CREATED,
)
def finding_to_task(
    finding_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Task:
    finding = _load_finding(finding_id, db)
    research = _load_project(finding.project_id, db)
    # The task belongs to the attached build project when there is one.
    task = Task(
        user_id=user.id,
        project_id=research.research_target_id or finding.project_id,
        title=finding.title,
        status="open",
    )
    db.add(task)
    finding.status = "tasked"
    db.commit()
    db.refresh(task)
    return task


@router.post(
    "/findings/{finding_id}/to-update",
    response_model=ProjectUpdateRead,
    status_code=http_status.HTTP_201_CREATED,
)
def finding_to_update(
    finding_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProjectUpdate:
    finding = _load_finding(finding_id, db)
    research = _load_project(finding.project_id, db)
    if research.research_target_id is None:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            "the research project is not attached to a build project",
        )
    update = ProjectUpdate(
        project_id=research.research_target_id,
        kind="research_finding",
        title=finding.title,
        body=finding.detail,
        source_ref={
            "type": "research_finding",
            "finding_id": finding.id,
            "research_project_id": finding.project_id,
        },
    )
    db.add(update)
    finding.status = "logged"
    db.commit()
    db.refresh(update)
    return update


@router.post(
    "/findings/{finding_id}/to-knowledge",
    response_model=KnowledgeEntryRead,
    status_code=http_status.HTTP_201_CREATED,
)
def finding_to_knowledge(
    finding_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> KnowledgeEntry:
    finding = _load_finding(finding_id, db)
    content = finding.title if not finding.detail else f"{finding.title}: {finding.detail}"
    entry = KnowledgeEntry(
        kind="fact",
        scope="development",
        source="connector",
        content=content,
        confidence=0.6,
        status="active",
        provenance={
            "from": "research_finding",
            "finding_id": finding.id,
            "research_project_id": finding.project_id,
            "url": finding.url,
        },
    )
    db.add(entry)
    finding.status = "saved"
    db.commit()
    db.refresh(entry)
    return entry
