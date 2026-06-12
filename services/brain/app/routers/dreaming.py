"""Dreaming endpoints: manual trigger, candidate review queue, and run history.

Accepting a candidate is the only path from the review queue into the Knowledge base. It
creates a knowledge_entry with source dreaming and marks the candidate accepted. Dismissing
marks it dismissed. Candidates are never deleted.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.agents.dreaming import run_dream
from app.db import get_db
from app.models.base import utcnow
from app.models.dreaming import DreamRun, MemoryCandidate
from app.models.knowledge import KnowledgeEntry
from app.models.user import User
from app.schemas.dreaming import (
    CandidateStatus,
    DreamRunRead,
    MemoryCandidateRead,
    MemoryFacet,
)
from app.schemas.knowledge import KnowledgeEntryRead
from app.security.auth import current_user

router = APIRouter(prefix="/dreaming", tags=["dreaming"])


def _load_candidate(candidate_id: int, db: Session) -> MemoryCandidate:
    candidate = db.get(MemoryCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "candidate not found")
    return candidate


@router.post("/run", response_model=DreamRunRead, status_code=http_status.HTTP_201_CREATED)
def trigger_run(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> DreamRun:
    # Manual trigger for development. The nightly schedule calls the same service.
    return run_dream(db, trigger="manual")


@router.get("/candidates", response_model=list[MemoryCandidateRead])
def list_candidates(
    facet: MemoryFacet | None = Query(default=None),
    status: CandidateStatus | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[MemoryCandidate]:
    query = db.query(MemoryCandidate)
    if facet is not None:
        query = query.filter(MemoryCandidate.facet == facet)
    if status is not None:
        query = query.filter(MemoryCandidate.status == status)
    return query.order_by(MemoryCandidate.created_at.desc(), MemoryCandidate.id.desc()).all()


@router.post("/candidates/{candidate_id}/accept", response_model=KnowledgeEntryRead)
def accept_candidate(
    candidate_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> KnowledgeEntry:
    candidate = _load_candidate(candidate_id, db)
    if candidate.status != "pending":
        raise HTTPException(
            http_status.HTTP_409_CONFLICT, f"candidate is already {candidate.status}"
        )

    entry = KnowledgeEntry(
        kind=candidate.kind,
        scope=candidate.scope,
        source="dreaming",
        content=candidate.content,
        confidence=candidate.confidence,
        status="active",
        provenance={
            "from": "memory_candidate",
            "candidate_id": candidate.id,
            "facet": candidate.facet,
            "source_refs": candidate.source_refs,
        },
    )
    db.add(entry)

    candidate.status = "accepted"
    candidate.reviewed_at = utcnow()
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/candidates/{candidate_id}/dismiss", response_model=MemoryCandidateRead)
def dismiss_candidate(
    candidate_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MemoryCandidate:
    candidate = _load_candidate(candidate_id, db)
    if candidate.status != "pending":
        raise HTTPException(
            http_status.HTTP_409_CONFLICT, f"candidate is already {candidate.status}"
        )
    candidate.status = "dismissed"
    candidate.reviewed_at = utcnow()
    db.commit()
    db.refresh(candidate)
    return candidate


@router.get("/runs", response_model=list[DreamRunRead])
def list_runs(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[DreamRun]:
    return db.query(DreamRun).order_by(DreamRun.created_at.desc(), DreamRun.id.desc()).all()
