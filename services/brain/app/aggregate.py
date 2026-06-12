"""Flow item aggregation.

Assembles a single FlowItem DTO from the item, its decision record, its linked project,
and the on disk plan and preview. Read only, it does not mutate state.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.models.inbox import ClassificationRecord, InboxItem
from app.models.project import Project
from app.safety import PathSafetyError, ensure_within_root
from app.schemas.entities import ClassificationRecordRead
from app.schemas.flow import FlowItemDTO
from app.settings import get_settings


def _gate_state(project: Project | None) -> str:
    if project is None:
        return "none"
    if project.stage in ("approved", "build"):
        return "approved"
    if project.stage == "rejected":
        return "rejected"
    if project.stage in ("process", "clarify"):
        return "waiting"
    return "none"


def _exists_within(root: str, relative_or_path: str | Path) -> bool:
    try:
        return ensure_within_root(root, relative_or_path).exists()
    except (PathSafetyError, OSError):
        return False


def build_flow_item(db: Session, item: InboxItem) -> FlowItemDTO:
    settings = get_settings()
    record = (
        db.query(ClassificationRecord)
        .filter(ClassificationRecord.item_id == item.id)
        .order_by(ClassificationRecord.created_at.desc(), ClassificationRecord.id.desc())
        .first()
    )
    project = db.query(Project).filter(Project.item_id == item.id).first()

    plan_available = bool(
        project
        and project.plan_path
        and _exists_within(settings.nexa_projects_root, project.plan_path)
    )
    preview_available = bool(
        project
        and _exists_within(
            settings.nexa_projects_root, Path(project.slug) / "project_preview.html"
        )
    )

    return FlowItemDTO(
        id=item.id,
        name=item.name,
        source=item.source,
        status=item.status,
        created_at=item.created_at,
        classification=ClassificationRecordRead.model_validate(record) if record else None,
        route=record.recommended_route if record else None,
        project_id=project.id if project else None,
        project_stage=project.stage if project else None,
        plan_available=plan_available,
        preview_available=preview_available,
        build_destination=project.build_destination if project else None,
        selected_integrations=project.selected_integrations if project else [],
        gate_state=_gate_state(project),
    )
