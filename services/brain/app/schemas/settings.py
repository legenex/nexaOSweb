"""Intake knob, general workspace, and knowledge policy schemas."""

from typing import Literal

from pydantic import BaseModel, Field

Appearance = Literal["system", "dark", "light"]


class GeneralSettings(BaseModel):
    """Workspace level general settings, the defaults that frame the other surfaces.

    general_instructions is the system level instruction prepended to model work. The rest are
    presentation and locale preferences.
    """

    general_instructions: str
    timezone: str
    appearance: str
    language: str
    notifications: bool


class GeneralSettingsPatch(BaseModel):
    general_instructions: str | None = None
    timezone: str | None = None
    appearance: Appearance | None = None
    language: str | None = None
    notifications: bool | None = None


class IntakeSettings(BaseModel):
    confidence_threshold: float
    classify_sweep_enabled: bool
    classify_sweep_interval: int
    classify_batch: int


class IntakeSettingsPatch(BaseModel):
    confidence_threshold: float | None = None
    classify_sweep_enabled: bool | None = None
    classify_sweep_interval: int | None = None
    classify_batch: int | None = None


class KnowledgePolicy(BaseModel):
    """What the system may ingest, and what is allowed into long term memory.

    The memory gate stays human by default: require_approval is on and connector memory is
    off, so nothing reaches the Knowledge base without an explicit accept in the Dreaming
    review queue.
    """

    ingest_chatgpt_api: bool
    ingest_claude_api: bool
    ingest_connectors: bool
    memory_require_approval: bool
    memory_allow_dreaming: bool
    memory_allow_connectors: bool
    memory_min_confidence: float


class KnowledgePolicyPatch(BaseModel):
    ingest_chatgpt_api: bool | None = None
    ingest_claude_api: bool | None = None
    ingest_connectors: bool | None = None
    memory_require_approval: bool | None = None
    memory_allow_dreaming: bool | None = None
    memory_allow_connectors: bool | None = None
    memory_min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
