"""FastAPI application entry point.

Wires CORS from settings and exposes the health probe. Routers are registered here as
later prompts add them. On boot it logs the resolved storage paths and reconciles the durable
owner and admin accounts so login survives a database move.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agents.scheduler import register_scheduler
from .db import SessionLocal
from .routers import (
    auth,
    dashboard,
    dreaming,
    flow,
    focus,
    insights,
    intake,
    integrations,
    journal,
    knowledge,
    model_config,
    projects,
    providers,
    research,
    runtime,
    skills,
    system,
    tasks,
    users,
)
from .routers import settings as settings_router
from .seed import seed_accounts
from .settings import get_settings, log_storage_paths

# Ensure the nexaos log namespace emits at INFO. Uvicorn configures its own loggers but does not
# attach a handler to application loggers, so without this the boot storage and seed lines would be
# silently dropped, defeating the point of logging the resolved paths.
_nexa_logger = logging.getLogger("nexaos")
if not _nexa_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
    _nexa_logger.addHandler(_handler)
    _nexa_logger.setLevel(logging.INFO)
    _nexa_logger.propagate = False

logger = logging.getLogger("nexaos.boot")

settings = get_settings()

app = FastAPI(title="nexaOSweb Brain", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(intake.router)
app.include_router(journal.router)
app.include_router(flow.router)
app.include_router(projects.router)
app.include_router(research.router)
app.include_router(runtime.router)
app.include_router(insights.router)
app.include_router(focus.router)
app.include_router(knowledge.router)
app.include_router(dreaming.router)
app.include_router(model_config.router)
app.include_router(providers.router)
app.include_router(system.router)
app.include_router(settings_router.router)
app.include_router(users.router)
app.include_router(integrations.router)
app.include_router(skills.router)
app.include_router(tasks.router)

register_scheduler(app)


@app.on_event("startup")
def _boot() -> None:
    """Log the resolved storage paths, then reconcile the durable owner and admin accounts.

    Logging the paths first makes a wrong, working directory dependent location obvious in the
    logs. The seed is gated by NEXA_SEED_ON_BOOT and is skipped under pytest so the test suite,
    which talks to its own in memory database, never writes to the canonical store.
    """
    log_storage_paths(settings)
    if settings.nexa_seed_on_boot and "PYTEST_CURRENT_TEST" not in os.environ:
        with SessionLocal() as db:
            seed_accounts(db)


@app.get("/healthz", tags=["health"])
def healthz() -> dict[str, str]:
    """Liveness probe used by CI and the deploy verification step."""
    return {"status": "ok"}
