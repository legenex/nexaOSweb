"""Skills and connectors read schemas."""

from pydantic import BaseModel


class SkillEntry(BaseModel):
    id: str
    label: str
    description: str
    model_key: str
    resolved_model: str | None = None


class ConnectorHealth(BaseModel):
    provider: str
    status: str


class SkillsResponse(BaseModel):
    skills: list[SkillEntry]
    connectors: list[ConnectorHealth]
