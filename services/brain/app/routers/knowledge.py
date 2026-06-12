"""Knowledge base CRUD.

List with optional filters, create, partial update, and a soft archive that flips status
only. Entries are never deleted, in line with the additive only data rule.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.knowledge import KnowledgeEntry
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeEntryCreate,
    KnowledgeEntryRead,
    KnowledgeEntryUpdate,
    KnowledgeKind,
    KnowledgeScope,
    KnowledgeSource,
    KnowledgeStatus,
)
from app.security.auth import current_user

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _load(entry_id: int, db: Session) -> KnowledgeEntry:
    entry = db.get(KnowledgeEntry, entry_id)
    if entry is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "knowledge entry not found")
    return entry


@router.get("", response_model=list[KnowledgeEntryRead])
def list_knowledge(
    scope: KnowledgeScope | None = Query(default=None),
    kind: KnowledgeKind | None = Query(default=None),
    status: KnowledgeStatus | None = Query(default=None),
    source: KnowledgeSource | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[KnowledgeEntry]:
    query = db.query(KnowledgeEntry)
    if scope is not None:
        query = query.filter(KnowledgeEntry.scope == scope)
    if kind is not None:
        query = query.filter(KnowledgeEntry.kind == kind)
    if status is not None:
        query = query.filter(KnowledgeEntry.status == status)
    if source is not None:
        query = query.filter(KnowledgeEntry.source == source)
    return query.order_by(
        KnowledgeEntry.updated_at.desc(), KnowledgeEntry.id.desc()
    ).all()


@router.post("", response_model=KnowledgeEntryRead, status_code=http_status.HTTP_201_CREATED)
def create_knowledge(
    payload: KnowledgeEntryCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> KnowledgeEntry:
    entry = KnowledgeEntry(**payload.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=KnowledgeEntryRead)
def update_knowledge(
    entry_id: int,
    payload: KnowledgeEntryUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> KnowledgeEntry:
    entry = _load(entry_id, db)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/{entry_id}/archive", response_model=KnowledgeEntryRead)
def archive_knowledge(
    entry_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> KnowledgeEntry:
    # Soft archive. Status only, the row is preserved.
    entry = _load(entry_id, db)
    entry.status = "archived"
    db.commit()
    db.refresh(entry)
    return entry
