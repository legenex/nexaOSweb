"""Skills and connectors, read only.

Agent facing skills are the agents declared in config/models.yaml, each resolved through the
model router so the concrete model is shown without hardcoding an id. Connector health is the
set of integrations the user has, surfaced as provider plus status. There is no write surface
here yet, so this is a read only listing with a clear empty state on the client.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.project import Integration
from app.models.user import User
from app.router import model_router
from app.schemas.skills import ConnectorHealth, SkillEntry, SkillsResponse
from app.security.auth import current_user

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=SkillsResponse)
def list_skills(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SkillsResponse:
    config = model_router.load_config()
    models: dict = config.get("models", {})
    agents: dict = config.get("agents", {})

    skills: list[SkillEntry] = []
    for agent_id, spec in agents.items():
        model_key = str(spec.get("model_key", ""))
        resolved = models.get(model_key, {}).get("model") if model_key in models else None
        skills.append(
            SkillEntry(
                id=agent_id,
                label=str(spec.get("label", agent_id)),
                description=str(spec.get("description", "")),
                model_key=model_key,
                resolved_model=resolved,
            )
        )

    connectors = [
        ConnectorHealth(provider=row.provider, status=row.status)
        for row in db.query(Integration)
        .filter(Integration.user_id == user.id)
        .order_by(Integration.provider.asc())
        .all()
    ]
    return SkillsResponse(skills=skills, connectors=connectors)
