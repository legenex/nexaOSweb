"""Agent governance read endpoints.

Reads only. The audit log is append-only and authored solely through the writer in app/audit.py;
there is no write route here by design. Two projections of the log: the cross run audit feed,
filterable by project, run, category, and actor, and a per project view.

Every row is scoped to the requesting user the same way the runtime reads scope their runs: a row
tied to a project is visible only to that project's owner, and a row tied to no project is a
system event visible to any authenticated user. project_id is backfilled at write time, so the
scope check is a single column lookup per row.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.access import user_owns_project
from app.audit import CATEGORY_ACTIONS
from app.db import get_db
from app.models.audit import AgentAudit
from app.models.user import User
from app.schemas.audit import AuditRead
from app.security.auth import current_user

router = APIRouter(prefix="/agents", tags=["agents"])

# A read cap so a single call can never stream the whole log. The reads are newest first, so the
# default window is the most recent activity; a caller paginates with a tighter filter.
_DEFAULT_LIMIT = 200
_MAX_LIMIT = 1000


def _visible(rows: list[AgentAudit], user: User, db: Session) -> list[AgentAudit]:
    return [row for row in rows if user_owns_project(row.project_id, user, db)]


@router.get("/audit", response_model=list[AuditRead])
def list_audit(
    project_id: int | None = Query(None),
    run_id: int | None = Query(None),
    category: str | None = Query(None),
    actor: str | None = Query(None),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[AgentAudit]:
    """The cross run governance feed, newest first, filterable by project, run, category, actor."""
    if category is not None and category not in CATEGORY_ACTIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown category {category!r}")
    if project_id is not None and not user_owns_project(project_id, user, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")

    query = db.query(AgentAudit)
    if project_id is not None:
        query = query.filter(AgentAudit.project_id == project_id)
    if run_id is not None:
        query = query.filter(AgentAudit.run_id == run_id)
    if category is not None:
        query = query.filter(AgentAudit.category == category)
    if actor is not None:
        query = query.filter(AgentAudit.actor == actor)
    rows = query.order_by(AgentAudit.created_at.desc(), AgentAudit.id.desc()).all()
    return _visible(rows, user, db)[:limit]


@router.get("/projects/{project_id}/audit", response_model=list[AuditRead])
def list_project_audit(
    project_id: int,
    category: str | None = Query(None),
    actor: str | None = Query(None),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[AgentAudit]:
    """Every governance event recorded for one project, newest first."""
    if not user_owns_project(project_id, user, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    if category is not None and category not in CATEGORY_ACTIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown category {category!r}")

    query = db.query(AgentAudit).filter(AgentAudit.project_id == project_id)
    if category is not None:
        query = query.filter(AgentAudit.category == category)
    if actor is not None:
        query = query.filter(AgentAudit.actor == actor)
    rows = query.order_by(AgentAudit.created_at.desc(), AgentAudit.id.desc()).all()
    return rows[:limit]
