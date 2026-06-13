"""Projects workspace request and read schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectModeRead(BaseModel):
    key: str
    label: str
    capture_questions: list[str]
    required_files: list[str]
    build_destination: str


class SetModeRequest(BaseModel):
    mode: str


class ProjectRenameRequest(BaseModel):
    name: str


class DeleteFileResponse(BaseModel):
    path: str
    deleted: bool


class ConnectedIntegration(BaseModel):
    provider: str
    status: str  # "connected" or "available"
    integration_id: int | None = None


class ProjectOverview(BaseModel):
    id: int
    name: str
    type: str  # the project mode
    status: str
    stage: str
    url: str | None = None
    repo: str | None = None
    local_path: str | None = None
    build_destination: str | None = None
    connected_integrations: list[ConnectedIntegration] = []
    last_updated: datetime
    priority: str | None = None
    revenue_potential: str | None = None
    current_blocker: str | None = None
    next_recommended_action: str | None = None


class WorkspaceUpdate(BaseModel):
    """Editable overview fields. Only provided fields are written."""

    status: str | None = None
    url: str | None = None
    repo: str | None = None
    local_path: str | None = None
    priority: str | None = None
    revenue_potential: str | None = None
    current_blocker: str | None = None
    next_recommended_action: str | None = None


class FileNode(BaseModel):
    path: str  # relative to the project folder
    type: str  # "file" or "dir"
    size: int | None = None


class RequiredFileStatus(BaseModel):
    path: str
    present: bool


class FilesResponse(BaseModel):
    tree: list[FileNode]
    required_files: list[RequiredFileStatus]


class FileContent(BaseModel):
    path: str
    content: str


class BuildLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    action: str
    status: str
    summary: str
    file_path: str | None
    diff_summary: str
    created_at: datetime


class EditorProposeRequest(BaseModel):
    file_path: str
    instruction: str


class EditorProposal(BaseModel):
    proposal_id: int
    file_path: str
    summary: str
    diff_summary: str
    before_content: str | None
    after_content: str
    status: str


class EditorApplyRequest(BaseModel):
    proposal_id: int
    approved: bool = False


class EditorApplyResponse(BaseModel):
    build_log_id: int
    file_path: str
    status: str
    written_path: str


class RollbackRequest(BaseModel):
    build_log_id: int


class RollbackResponse(BaseModel):
    build_log_id: int
    file_path: str
    status: str
