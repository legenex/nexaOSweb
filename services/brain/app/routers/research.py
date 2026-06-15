"""Research to project link, runs, and finding level actions.

A research project attaches to a build project, runs produce findings, and each finding can
become a task, a project update, or a saved knowledge entry. Attaching a run target makes a
completed run post its findings into the build project's Update Log.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.agents.research import generate_config, run_research
from app.db import get_db
from app.json_extract import ModelUnavailableError
from app.models.knowledge import KnowledgeEntry
from app.models.project import Project
from app.models.research import ProjectUpdate, ResearchFinding, ResearchRun
from app.models.user import User
from app.models.workspace import Task
from app.offline import has_provider_keys
from app.project_modes import DEFAULT_MODE, is_valid_mode
from app.schemas.entities import ProjectRead, TaskRead
from app.schemas.knowledge import KnowledgeEntryRead
from app.schemas.research import (
    AttachRequest,
    CreateProjectFromResearchRequest,
    GenerateConfigRequest,
    GenerateConfigResponse,
    ProjectUpdateRead,
    ResearchFindingRead,
    ResearchProjectCreate,
    ResearchProjectRead,
    ResearchProjectUpdate,
    ResearchRunRead,
)
from app.security.auth import current_user
from app.util import slugify

router = APIRouter(prefix="/research", tags=["research"])


def _model_unavailable_detail(action: str) -> str:
    """Honest 503 detail: distinguish no provider connected from a failed model call.

    Both surface as ModelUnavailableError, but the fix differs: a missing provider needs a key
    connected in Settings, Models and Agents, while a failed call points at the connected key.
    Naming the cause turns a dead end into a next step.
    """
    if has_provider_keys():
        return f"{action} is unavailable: the model call failed. Check the connected provider key."
    return (
        f"{action} is unavailable: no model provider is connected. "
        "Connect one in Settings, Models and Agents."
    )

# Default config so a project created before a field existed still reads cleanly.
_CONFIG_DEFAULTS = {
    "kind": "research",
    "topic": "",
    "purpose": "",
    "goals": [],
    "depth": "standard",
    "lookback": 30,
    "schedule": "off",
    "category": "general",
}


def _is_research(project: Project) -> bool:
    return bool(project.research_config) and project.research_config.get("kind") == "research"


def _is_active_research(project: Project) -> bool:
    # A research project that has not been soft deleted. Deletion sets a deleted flag in the
    # research_config blob (additive, no migration), so the row and its runs and findings are
    # preserved and the project is recoverable.
    return _is_research(project) and not project.research_config.get("deleted")


def _research_read(project: Project) -> ResearchProjectRead:
    config = {**_CONFIG_DEFAULTS, **(project.research_config or {})}
    return ResearchProjectRead(
        id=project.id,
        name=project.name,
        slug=project.slug,
        stage=project.stage,
        topic=str(config["topic"]),
        purpose=str(config["purpose"]),
        goals=list(config["goals"]),
        depth=str(config["depth"]),
        lookback=int(config["lookback"]),
        schedule=str(config["schedule"]),
        category=str(config["category"]),
        research_target_id=project.research_target_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _load_research_project(project_id: int, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None or not _is_active_research(project):
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "research project not found")
    return project


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


# --- research project CRUD ---------------------------------------------------------------


@router.get("/projects", response_model=list[ResearchProjectRead])
def list_research_projects(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ResearchProjectRead]:
    projects = (
        db.query(Project).order_by(Project.created_at.desc(), Project.id.desc()).all()
    )
    return [_research_read(p) for p in projects if _is_active_research(p)]


@router.post(
    "/projects", response_model=ResearchProjectRead, status_code=http_status.HTTP_201_CREATED
)
def create_research_project(
    payload: ResearchProjectCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ResearchProjectRead:
    project = Project(
        name=payload.name,
        slug=slugify(payload.name) or "research",
        stage="idea",
        research_config={
            "kind": "research",
            "topic": payload.topic,
            "purpose": payload.purpose,
            "goals": payload.goals,
            "depth": payload.depth,
            "lookback": payload.lookback,
            "schedule": payload.schedule,
            "category": payload.category,
        },
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _research_read(project)


@router.patch("/projects/{research_id}", response_model=ResearchProjectRead)
def update_research_project(
    research_id: int,
    payload: ResearchProjectUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ResearchProjectRead:
    project = _load_research_project(research_id, db)
    updates = payload.model_dump(exclude_none=True)
    if "name" in updates:
        project.name = updates.pop("name")
    if updates:
        project.research_config = {**(project.research_config or {}), **updates}
    db.commit()
    db.refresh(project)
    return _research_read(project)


@router.delete("/projects/{research_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_research_project(
    research_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    project = _load_research_project(research_id, db)
    # Soft delete: flag the project deleted in its research_config and keep the row plus its
    # runs and findings, so a removed research project stays recoverable rather than being
    # physically destroyed.
    project.research_config = {**(project.research_config or {}), "deleted": True}
    db.commit()


@router.post(
    "/projects/{research_id}/duplicate",
    response_model=ResearchProjectRead,
    status_code=http_status.HTTP_201_CREATED,
)
def duplicate_research_project(
    research_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ResearchProjectRead:
    source = _load_research_project(research_id, db)
    name = f"{source.name} (copy)"
    copy = Project(
        name=name,
        slug=slugify(name) or "research-copy",
        stage="idea",
        research_config={**(source.research_config or {}), "kind": "research"},
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return _research_read(copy)


@router.post("/generate-config", response_model=GenerateConfigResponse)
def generate_research_config(
    payload: GenerateConfigRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> GenerateConfigResponse:
    # Require a real model: never present the offline placeholder fallback as a generated draft.
    try:
        draft = generate_config(payload.topic, payload.name, allow_offline=False)
    except ModelUnavailableError as exc:
        raise HTTPException(
            http_status.HTTP_503_SERVICE_UNAVAILABLE,
            _model_unavailable_detail("Generate with AI"),
        ) from exc
    return GenerateConfigResponse(**draft)


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


@router.post(
    "/{research_id}/create-project",
    response_model=ProjectRead,
    status_code=http_status.HTTP_201_CREATED,
)
def create_project_from_research(
    research_id: int,
    payload: CreateProjectFromResearchRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Project:
    """Create a build project from a research project and attach the research to it in one step."""
    research = _load_project(research_id, db)
    name = (payload.name or research.name or "Research project").strip()[:300] or "Research project"
    mode = payload.mode if is_valid_mode(payload.mode) else DEFAULT_MODE
    project = Project(item_id=None, name=name, slug=slugify(name), stage="idea", mode=mode)
    db.add(project)
    db.flush()
    research.research_target_id = project.id
    db.commit()
    db.refresh(project)
    return project


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
    # Require a real model so a run never writes placeholder findings as if generated.
    try:
        run = run_research(db, research, allow_offline=False)
    except ModelUnavailableError as exc:
        raise HTTPException(
            http_status.HTTP_503_SERVICE_UNAVAILABLE,
            _model_unavailable_detail("Run"),
        ) from exc
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
        status="todo",
        source="research",
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
