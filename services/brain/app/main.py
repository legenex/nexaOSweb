"""FastAPI application entry point.

Wires CORS from settings and exposes the health probe. Routers are registered here as
later prompts add them.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agents.scheduler import register_scheduler
from .routers import (
    auth,
    dashboard,
    dreaming,
    flow,
    insights,
    intake,
    knowledge,
    model_config,
    projects,
    research,
    system,
)
from .routers import settings as settings_router
from .settings import get_settings

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
app.include_router(flow.router)
app.include_router(projects.router)
app.include_router(research.router)
app.include_router(insights.router)
app.include_router(knowledge.router)
app.include_router(dreaming.router)
app.include_router(model_config.router)
app.include_router(system.router)
app.include_router(settings_router.router)

register_scheduler(app)


@app.get("/healthz", tags=["health"])
def healthz() -> dict[str, str]:
    """Liveness probe used by CI and the deploy verification step."""
    return {"status": "ok"}
