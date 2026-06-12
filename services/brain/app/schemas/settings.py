"""Intake knob schemas."""

from pydantic import BaseModel


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
