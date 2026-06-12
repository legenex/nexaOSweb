"""Schemas for the Models and Agents settings surface.

The registry mirrors config/models.yaml: each semantic key with its concrete model, the
default sampling, and a coarse cost hint, plus the agents and the key each runs through.
The frontend never names a model id; it remaps a key here and the router picks it up.
"""

from pydantic import BaseModel, Field, field_validator

# A provider prefixed model id, for example anthropic/claude-sonnet-4-6.
_MODEL_PATTERN = r"^[A-Za-z0-9._-]+/[A-Za-z0-9./:_-]+$"
# A semantic key, lower snake case.
_KEY_PATTERN = r"^[a-z][a-z0-9_]*$"


class CostHint(BaseModel):
    tier: str
    label: str
    blended_per_mtok: float | None = None


class ModelEntry(BaseModel):
    key: str
    model: str
    temperature: float | None = None
    max_tokens: int | None = None
    cost: CostHint


class AgentBinding(BaseModel):
    id: str
    label: str
    description: str
    model_key: str
    # The concrete model the key resolves to, or null if the key is missing.
    resolved_model: str | None = None


class ModelsConfig(BaseModel):
    keys: list[ModelEntry]
    agents: list[AgentBinding]


class RemapKeyRequest(BaseModel):
    model: str = Field(pattern=_MODEL_PATTERN)
    temperature: float | None = None
    max_tokens: int | None = None


class AddModelRequest(BaseModel):
    key: str = Field(pattern=_KEY_PATTERN, max_length=60)
    model: str = Field(pattern=_MODEL_PATTERN)
    temperature: float | None = None
    max_tokens: int | None = None

    @field_validator("key")
    @classmethod
    def _not_reserved(cls, value: str) -> str:
        if value == "agents":
            raise ValueError("'agents' is reserved")
        return value
