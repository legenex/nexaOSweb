"""System (Connection) settings.

Reports Brain connection and health, version, database and migration status, and a process
health view, and offers a one click restart with a server side confirm. The restart
re-executes the current process; under a supervisor (systemd, Plesk) the fresh process
takes over, which is the fix for the recurring stale process issue.
"""

import os
import platform
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.db import engine
from app.models.user import User
from app.schemas.system import (
    DatabaseHealth,
    MigrationHealth,
    ProcessHealth,
    RestartRequest,
    RestartResponse,
    SystemHealth,
)
from app.security.auth import current_user
from app.settings import get_settings

router = APIRouter(prefix="/system", tags=["system"])

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

# Captured at import so uptime is measured from process start.
_STARTED_AT = time.time()
_STARTED_AT_ISO = datetime.fromtimestamp(_STARTED_AT, tz=timezone.utc).isoformat()

# A short grace so the HTTP response is flushed before the process is replaced. Tests
# shorten this and replace the hook so pytest is never actually re-executed.
RESTART_DELAY_SECONDS = 0.5


def _exec_restart() -> None:  # pragma: no cover - replaces the running process
    os.execv(sys.executable, [sys.executable, *sys.argv])


# Swapped in tests to a recorder so the real exec never fires.
_restart_hook: Callable[[], None] = _exec_restart


def _mask_url(url: str) -> str:
    parsed = make_url(url)
    if parsed.password:
        parsed = parsed.set(password="***")
    return str(parsed)


def _database_health() -> DatabaseHealth:
    connected = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any failure means not connected
        connected = False
    return DatabaseHealth(
        dialect=engine.dialect.name,
        url=_mask_url(str(engine.url)),
        connected=connected,
    )


def _migration_health() -> MigrationHealth:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    current: str | None = None
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    except Exception:  # noqa: BLE001 - missing version table reads as not stamped
        current = None
    return MigrationHealth(
        current=current,
        head=head,
        up_to_date=current is not None and current == head,
    )


def _process_health() -> ProcessHealth:
    return ProcessHealth(
        pid=os.getpid(),
        python_version=platform.python_version(),
        started_at=_STARTED_AT_ISO,
        uptime_seconds=round(time.time() - _STARTED_AT, 3),
    )


@router.get("/health", response_model=SystemHealth)
def get_health(
    request: Request,
    user: User = Depends(current_user),
) -> SystemHealth:
    return SystemHealth(
        status="ok",
        version=request.app.version,
        sweep_enabled=get_settings().classify_sweep_enabled,
        process=_process_health(),
        database=_database_health(),
        migration=_migration_health(),
    )


@router.post("/restart", response_model=RestartResponse)
def restart_brain(
    payload: RestartRequest,
    user: User = Depends(current_user),
) -> RestartResponse:
    if not payload.confirm:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            "restart requires confirm: true",
        )
    timer = threading.Timer(RESTART_DELAY_SECONDS, _restart_hook)
    timer.daemon = True
    timer.start()
    return RestartResponse(scheduled=True, delay_seconds=RESTART_DELAY_SECONDS)
