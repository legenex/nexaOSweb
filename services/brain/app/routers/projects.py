"""Projects listing, the human gate, and the Projects workspace.

The workspace exposes a project overview, its files tree and content, the build log, the
update log, a project mode setter, and a gated AI editor. The editor proposes a change and
returns a diff summary, writing nothing until an explicit approval arrives. Every file read
and write is confined to the project's own folder by the path safety gate.

Card level actions on a project (rename, duplicate, delete) and file deletion in the
workspace live here too. Delete is a soft delete: it flags the project deleted in its
workspace blob and keeps the row, its files, and its history, so a removed project is
recoverable rather than physically destroyed.
"""

import shutil
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
    DeleteFileResponse,
    EditorApplyRequest,
    EditorApplyResponse,
    EditorProposal,
    EditorProposeRequest,
    FileContent,
    FileNode,
    FilesResponse,
    ProjectModeRead,
    ProjectOverview,
    ProjectRenameRequest,
    RequiredFileStatus,
    RollbackRequest,
    RollbackResponse,
    SetModeRequest,
    WorkspaceUpdate,
)
from app.schemas.research import ProjectUpdateRead
from app.security.auth import current_user
from app.settings import get_settings
from app.util import slugify

router = APIRouter(prefix="/projects", tags=["projects"])

# Walk caps so a runaway tree cannot exhaust a request.
_MAX_FILES = 2000


def _is_deleted(project: Project) -> bool:
    # A soft deleted project carries a deleted flag, set by build projects in the workspace
    # blob and by research projects in research_config. Either hides the project from its list.
    return bool((project.workspace or {}).get("deleted")) or bool(
        (project.research_config or {}).get("deleted")
    )


def _load_owned_project(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None or _is_deleted(project):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    if project.item_id is not None:
        item = db.get(InboxItem, project.item_id)
        if item is None or item.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return project


def _unique_slug(db: Session, base: str) -> str:
    """Return a project slug not already taken on disk identity, suffixing -2, -3 as needed."""
    candidate = base or "project"
    existing = {row.slug for row in db.query(Project.slug).all()}
    if candidate not in existing:
        return candidate
    suffix = 2
    while f"{candidate}-{suffix}"[:160] in existing:
        suffix += 1
    return f"{candidate}-{suffix}"[:160]


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
    # Soft deleted projects are excluded so a removed project leaves the list.
    owned_item_ids = [
        row.id for row in db.query(InboxItem.id).filter(InboxItem.user_id == user.id).all()
    ]
    projects = (
        db.query(Project)
        .filter((Project.item_id.in_(owned_item_ids)) | (Project.item_id.is_(None)))
        .order_by(Project.created_at.desc(), Project.id.desc())
        .all()
    )
    return [project for project in projects if not _is_deleted(project)]


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


@router.patch("/{project_id}", response_model=ProjectRead)
def rename_project(
    project_id: int,
    payload: ProjectRenameRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Project:
    project = _load_owned_project(project_id, user, db)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "name cannot be empty")
    # The slug stays fixed: it is the on disk folder identity. Only the display name changes.
    project.name = name[:300]
    db.commit()
    db.refresh(project)
    return project


@router.post(
    "/{project_id}/duplicate", response_model=ProjectRead, status_code=status.HTTP_201_CREATED
)
def duplicate_project(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Project:
    source = _load_owned_project(project_id, user, db)
    name = f"{source.name} (copy)"
    slug = _unique_slug(db, slugify(name, fallback="project-copy"))
    # The copy carries the same mode, plan, destination, integrations, and config, but starts
    # fresh at the idea stage and is not soft deleted regardless of the source flag.
    workspace = {k: v for k, v in (source.workspace or {}).items() if k != "deleted"}
    research_config = {
        k: v for k, v in (source.research_config or {}).items() if k != "deleted"
    }
    copy = Project(
        item_id=source.item_id,
        name=name[:300],
        slug=slug,
        stage="idea",
        mode=source.mode,
        plan_json=dict(source.plan_json or {}),
        build_destination=source.build_destination,
        selected_integrations=list(source.selected_integrations or []),
        workspace=workspace,
        research_target_id=source.research_target_id,
        research_config=research_config,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)

    # Copy the on disk project folder, if any, into the new slug folder. Both paths are gated.
    settings = get_settings()
    src_dir = ensure_within_root(settings.nexa_projects_root, source.slug)
    dst_dir = ensure_within_root(settings.nexa_projects_root, copy.slug)
    if src_dir.exists() and src_dir.is_dir() and not dst_dir.exists():
        shutil.copytree(src_dir, dst_dir)
        # The plan path, if set, pointed at the source folder; repoint it at the copy.
        if source.plan_path:
            plan_name = Path(source.plan_path).name
            copy.plan_path = str(dst_dir / plan_name)
            db.commit()
            db.refresh(copy)
    return copy


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    project = _load_owned_project(project_id, user, db)
    # Soft delete: flag the project deleted in its workspace blob and keep the row, its files
    # on disk, and its build and update history, so a removed project stays recoverable.
    project.workspace = {**(project.workspace or {}), "deleted": True}
    db.commit()


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


@router.delete("/{project_id}/files", response_model=DeleteFileResponse)
def delete_file(
    project_id: int,
    path: str = Query(..., description="path relative to the project folder"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> DeleteFileResponse:
    project = _load_owned_project(project_id, user, db)
    settings = get_settings()
    project_dir = ensure_within_root(settings.nexa_projects_root, project.slug)
    try:
        target = ensure_within_root(project_dir, path)
    except PathSafetyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "path escapes the project folder") from exc
    if target == project_dir:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot delete the project folder")
    if not target.exists() or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")

    # Snapshot the prior content for the audit log and possible recovery, when it is text.
    try:
        before = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        before = None

    relative = Path(path).as_posix()
    target.unlink()
    db.add(
        BuildLogEntry(
            project_id=project.id,
            action="delete",
            status="applied",
            summary=f"Deleted {relative}",
            file_path=relative,
            diff_summary=f"Removed file {relative}",
            before_content=before,
            after_content=None,
        )
    )
    db.commit()
    return DeleteFileResponse(path=relative, deleted=True)


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
