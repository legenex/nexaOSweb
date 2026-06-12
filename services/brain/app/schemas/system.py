"""Schemas for the System (Connection) settings surface.

Brain connection and health, version, database and migration status, a process health
view, and the restart control that addresses the recurring stale process issue.
"""

from pydantic import BaseModel


class ProcessHealth(BaseModel):
    pid: int
    python_version: str
    started_at: str
    uptime_seconds: float


class DatabaseHealth(BaseModel):
    dialect: str
    url: str  # credentials masked
    connected: bool


class MigrationHealth(BaseModel):
    current: str | None
    head: str | None
    up_to_date: bool


class SystemHealth(BaseModel):
    status: str
    version: str
    sweep_enabled: bool
    process: ProcessHealth
    database: DatabaseHealth
    migration: MigrationHealth


class RestartRequest(BaseModel):
    confirm: bool = False


class RestartResponse(BaseModel):
    scheduled: bool
    delay_seconds: float
