"""Intake knob and knowledge policy schemas."""

from pydantic import BaseModel, Field


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
