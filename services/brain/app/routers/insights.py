"""Insights endpoints.

Reads the cached latest batch and refreshes on demand. Generation derives insights from the
Knowledge base and recent activity (see app.agents.insights). Each insight supports four
actions: save to knowledge, create task, create project, and dismiss.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.agents.insights import generate_insights, latest_run
from app.db import get_db
from app.models.insight import Insight, InsightRun
from app.models.knowledge import KnowledgeEntry
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Task
from app.schemas.insights import (
    CreateProjectResponse,
    CreateTaskResponse,
    InsightRead,
    InsightsResponse,
    SaveToKnowledgeResponse,
)
from app.security.auth import current_user
from app.util import slugify

router = APIRouter(prefix="/insights", tags=["insights"])

# Category to the knowledge kind and scope used when saving an insight to the Knowledge base.
_KNOWLEDGE_MAP = {
    "personal_pattern": ("pattern", "personal"),
    "work_pattern": ("pattern", "work"),
    "profile_summary": ("fact", "general"),
    "innovation": ("fact", "general"),
}

# Statuses that remain visible in the cached feed (dismissed and superseded drop out).
_VISIBLE = ("active", "saved", "tasked", "project_created")


def _load_active_insight(insight_id: int, user: User, db: Session) -> Insight:
    insight = db.get(Insight, insight_id)
    if insight is None or insight.user_id != user.id:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "insight not found")
    if insight.status != "active":
        raise HTTPException(
            http_status.HTTP_409_CONFLICT, f"insight is already {insight.status}"
        )
    return insight


def _build_response(run: InsightRun | None, db: Session) -> InsightsResponse:
    if run is None:
        return InsightsResponse(
            run_id=None,
            generated_at=None,
            extraction_model_key=None,
            synthesis_model_key=None,
        )
    rows = (
        db.query(Insight)
        .filter(Insight.run_id == run.id, Insight.status.in_(_VISIBLE))
        .order_by(Insight.confidence.desc(), Insight.id.asc())
        .all()
    )
    reads = [InsightRead.model_validate(row) for row in rows]
    profile = next((r for r in reads if r.category == "profile_summary"), None)
    return InsightsResponse(
        run_id=run.id,
        generated_at=run.finished_at or run.created_at,
        extraction_model_key=run.extraction_model_key,
        synthesis_model_key=run.synthesis_model_key,
        personal_patterns=[r for r in reads if r.category == "personal_pattern"],
        work_patterns=[r for r in reads if r.category == "work_pattern"],
        profile_summary=profile,
        innovation=[r for r in reads if r.category == "innovation"],
    )


@router.get("", response_model=InsightsResponse)
def get_insights(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> InsightsResponse:
    # Cached read. Generate lazily on the first request so the feed is never empty.
    run = latest_run(db, user.id)
    if run is None:
        run = generate_insights(db, user.id, trigger="lazy")
    return _build_response(run, db)


@router.post("/refresh", response_model=InsightsResponse)
def refresh_insights(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> InsightsResponse:
    # Force a new generation pass. Supersedes the prior active batch.
    run = generate_insights(db, user.id, trigger="manual")
    return _build_response(run, db)


@router.get("/runs/{run_id}", response_model=InsightsResponse)
def get_run(
    run_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> InsightsResponse:
    run = db.get(InsightRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "insight run not found")
    return _build_response(run, db)


@router.post(
    "/{insight_id}/save-to-knowledge",
    response_model=SaveToKnowledgeResponse,
    status_code=http_status.HTTP_201_CREATED,
)
def save_to_knowledge(
    insight_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SaveToKnowledgeResponse:
    insight = _load_active_insight(insight_id, user, db)
    kind, scope = _KNOWLEDGE_MAP.get(insight.category, ("fact", "general"))
    entry = KnowledgeEntry(
        kind=kind,
        scope=scope,
        source="manual",
        content=insight.body or insight.title,
        confidence=insight.confidence,
        status="active",
        provenance={
            "from": "insight",
            "insight_id": insight.id,
            "category": insight.category,
            "reasoning": insight.reasoning,
        },
    )
    db.add(entry)
    db.flush()
    insight.status = "saved"
    insight.action_ref = {"type": "knowledge", "id": entry.id}
    db.commit()
    db.refresh(entry)
    return SaveToKnowledgeResponse(
        insight_id=insight.id, knowledge_entry_id=entry.id, status=insight.status
    )


@router.post(
    "/{insight_id}/create-task",
    response_model=CreateTaskResponse,
    status_code=http_status.HTTP_201_CREATED,
)
def create_task(
    insight_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CreateTaskResponse:
    insight = _load_active_insight(insight_id, user, db)
    task = Task(user_id=user.id, project_id=None, title=insight.title[:300], status="todo")
    db.add(task)
    db.flush()
    insight.status = "tasked"
    insight.action_ref = {"type": "task", "id": task.id}
    db.commit()
    db.refresh(task)
    return CreateTaskResponse(insight_id=insight.id, task_id=task.id, status=insight.status)


@router.post(
    "/{insight_id}/create-project",
    response_model=CreateProjectResponse,
    status_code=http_status.HTTP_201_CREATED,
)
def create_project(
    insight_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CreateProjectResponse:
    insight = _load_active_insight(insight_id, user, db)
    project = Project(
        item_id=None,
        name=insight.title[:300],
        slug=slugify(insight.title),
        stage="idea",
        plan_json={"summary": insight.body, "objective": insight.title},
    )
    db.add(project)
    db.flush()
    insight.status = "project_created"
    insight.action_ref = {"type": "project", "id": project.id}
    db.commit()
    db.refresh(project)
    return CreateProjectResponse(
        insight_id=insight.id, project_id=project.id, status=insight.status
    )


@router.post("/{insight_id}/dismiss", response_model=InsightRead)
def dismiss(
    insight_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Insight:
    insight = _load_active_insight(insight_id, user, db)
    insight.status = "dismissed"
    db.commit()
    db.refresh(insight)
    return insight
