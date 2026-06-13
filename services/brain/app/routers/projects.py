"""Projects listing, the human gate, and the Projects workspace.

The workspace exposes a project overview, its files tree and content, the build log, the
update log, a project mode setter, and a gated AI editor. The editor proposes a change and
returns a diff summary, writing nothing until an explicit approval arrives. Every file read
and write is confined to the project's own folder by the path safety gate.
"""

from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.agents.project_editor import (
    EditorError,
    apply_edit,
    propose_edit,
    rollback_edit,
)
from app.db import get_db
from app.models.inbox import InboxItem
from app.models.project import BuildLogEntry, Integration, Project
from app.models.research import ProjectUpdate
from app.models.user import User
from app.project_modes import (
    PROJECT_MODES,
    destination_for,
    is_valid_mode,
    required_files_for,
)
from app.safety import PathSafetyError, ensure_within_root
from app.schemas.entities import ProjectRead
from app.schemas.projects import (
    BuildLogRead,
    ConnectedIntegration,
    EditorApplyRequest,
    EditorApplyResponse,
    EditorProposal,
    EditorProposeRequest,
    FileContent,
    FileNode,
    FilesResponse,
    ProjectModeRead,
    ProjectOverview,
    RequiredFileStatus,
    RollbackRequest,
    RollbackResponse,
    SetModeRequest,
    WorkspaceUpdate,
)
from app.schemas.research import ProjectUpdateRead
from app.security.auth import current_user
from app.settings import get_settings

router = APIRouter(prefix="/projects", tags=["projects"])

# Walk caps so a runaway tree cannot exhaust a request.
_MAX_FILES = 2000


def _load_owned_project(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    if project.item_id is not None:
        item = db.get(InboxItem, project.item_id)
        if item is None or item.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return project


def _connected_integrations(
    project: Project, user: User, db: Session
) -> list[ConnectedIntegration]:
    connected = {
        row.provider.lower(): row
        for row in db.query(Integration).filter(Integration.user_id == user.id).all()
    }
    out: list[ConnectedIntegration] = []
    for provider in project.selected_integrations or []:
        row = connected.get(str(provider).lower())
        out.append(
            ConnectedIntegration(
                provider=str(provider),
                status="connected" if row and row.status == "connected" else "available",
                integration_id=row.id if row else None,
            )
        )
    return out


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


@router.get("/modes", response_model=list[ProjectModeRead])
def list_modes(_user: User = Depends(current_user)) -> list[ProjectModeRead]:
    return [
        ProjectModeRead(
            key=mode.key,
            label=mode.label,
            capture_questions=mode.capture_questions,
            required_files=mode.required_files,
            build_destination=mode.build_destination,
        )
        for mode in PROJECT_MODES.values()
    ]


@router.post("/{project_id}/mode", response_model=ProjectRead)
def set_mode(
    project_id: int,
    payload: SetModeRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Project:
    project = _load_owned_project(project_id, user, db)
    if not is_valid_mode(payload.mode):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown project mode: {payload.mode}")
    project.mode = payload.mode
    # The mode sets the default build destination. A later Clarify scope change can override.
    project.build_destination = destination_for(payload.mode)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}/overview", response_model=ProjectOverview)
def overview(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProjectOverview:
    project = _load_owned_project(project_id, user, db)
    ws = project.workspace or {}
    plan = project.plan_json or {}
    next_steps = plan.get("recommended_next_steps") or []
    next_action = ws.get("next_recommended_action") or (
        next_steps[0] if isinstance(next_steps, list) and next_steps else None
    )
    return ProjectOverview(
        id=project.id,
        name=project.name,
        type=project.mode,
        status=ws.get("status") or "active",
        stage=project.stage,
        url=ws.get("url"),
        repo=ws.get("repo"),
        local_path=ws.get("local_path"),
        build_destination=project.build_destination,
        connected_integrations=_connected_integrations(project, user, db),
        last_updated=project.updated_at,
        priority=ws.get("priority"),
        revenue_potential=ws.get("revenue_potential"),
        current_blocker=ws.get("current_blocker"),
        next_recommended_action=next_action,
    )


@router.patch("/{project_id}/overview", response_model=ProjectOverview)
def update_overview(
    project_id: int,
    payload: WorkspaceUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProjectOverview:
    project = _load_owned_project(project_id, user, db)
    ws = dict(project.workspace or {})
    for key, value in payload.model_dump(exclude_unset=True).items():
        ws[key] = value
    project.workspace = ws
    db.commit()
    db.refresh(project)
    return overview(project_id, user, db)


@router.get("/{project_id}/files", response_model=FilesResponse)
def files(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> FilesResponse:
    project = _load_owned_project(project_id, user, db)
    settings = get_settings()
    project_dir = ensure_within_root(settings.nexa_projects_root, project.slug)

    tree: list[FileNode] = []
    if project_dir.exists():
        count = 0
        for path in sorted(project_dir.rglob("*")):
            if count >= _MAX_FILES:
                break
            relative = path.relative_to(project_dir).as_posix()
            if path.is_dir():
                tree.append(FileNode(path=relative, type="dir"))
            else:
                tree.append(FileNode(path=relative, type="file", size=path.stat().st_size))
            count += 1

    present = {node.path for node in tree if node.type == "file"}
    required = [
        RequiredFileStatus(path=name, present=name in present)
        for name in required_files_for(project.mode)
    ]
    return FilesResponse(tree=tree, required_files=required)


@router.get("/{project_id}/files/content", response_model=FileContent)
def file_content(
    project_id: int,
    path: str = Query(..., description="path relative to the project folder"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> FileContent:
    project = _load_owned_project(project_id, user, db)
    settings = get_settings()
    project_dir = ensure_within_root(settings.nexa_projects_root, project.slug)
    try:
        target = ensure_within_root(project_dir, path)
    except PathSafetyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "path escapes the project folder") from exc
    if not target.exists() or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "file is not text"
        ) from exc
    return FileContent(path=Path(path).as_posix(), content=content)


@router.get("/{project_id}/build-log", response_model=list[BuildLogRead])
def build_log(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[BuildLogEntry]:
    # The build log shows actioned entries: build, applied edits, and rollbacks. Pending
    # proposals are not part of the log until they are approved and applied.
    _load_owned_project(project_id, user, db)
    return (
        db.query(BuildLogEntry)
        .filter(
            BuildLogEntry.project_id == project_id,
            BuildLogEntry.status != "proposed",
        )
        .order_by(BuildLogEntry.created_at.desc(), BuildLogEntry.id.desc())
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


@router.post("/{project_id}/editor/propose", response_model=EditorProposal)
def editor_propose(
    project_id: int,
    payload: EditorProposeRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EditorProposal:
    project = _load_owned_project(project_id, user, db)
    try:
        entry = propose_edit(
            db, project, file_path=payload.file_path, instruction=payload.instruction
        )
    except PathSafetyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "path escapes the project folder") from exc
    except EditorError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return EditorProposal(
        proposal_id=entry.id,
        file_path=entry.file_path or payload.file_path,
        summary=entry.summary,
        diff_summary=entry.diff_summary,
        before_content=entry.before_content,
        after_content=entry.after_content or "",
        status=entry.status,
    )


@router.post("/{project_id}/editor/apply", response_model=EditorApplyResponse)
def editor_apply(
    project_id: int,
    payload: EditorApplyRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EditorApplyResponse:
    project = _load_owned_project(project_id, user, db)
    if not payload.approved:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "explicit approval is required to apply a change"
        )
    entry = db.get(BuildLogEntry, payload.proposal_id)
    if entry is None or entry.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposal not found")
    try:
        written = apply_edit(db, project, entry)
    except PathSafetyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "path escapes the project folder") from exc
    except EditorError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return EditorApplyResponse(
        build_log_id=entry.id,
        file_path=entry.file_path or "",
        status=entry.status,
        written_path=written,
    )


@router.post("/{project_id}/editor/rollback", response_model=RollbackResponse)
def editor_rollback(
    project_id: int,
    payload: RollbackRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RollbackResponse:
    project = _load_owned_project(project_id, user, db)
    entry = db.get(BuildLogEntry, payload.build_log_id)
    if entry is None or entry.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "build log entry not found")
    try:
        rollback_entry = rollback_edit(db, project, entry)
    except PathSafetyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "path escapes the project folder") from exc
    except EditorError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return RollbackResponse(
        build_log_id=rollback_entry.id,
        file_path=rollback_entry.file_path or "",
        status=rollback_entry.status,
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
