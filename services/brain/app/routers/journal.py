"""Journal endpoints.

Entry CRUD plus voice capture transcription. Entries carry text, an optional mood and tags, and
timestamps; they are soft deleted (a deleted entry keeps its row and stays recoverable) and feed
the nightly Dreaming consolidation as an input, human gated, never auto-writing Knowledge.

Transcription uploads audio that is transcribed through the transcription model key resolved by
the router (never a hardcoded model id). The audio is processed in memory and never written to
disk, consistent with the journal image rule. When no provider key backs the transcription model
the route returns 501 Not Implemented so the client can distinguish a genuinely unconfigured
Brain from a browser or upload failure.
"""

import io
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.base import utcnow
from app.models.user import User
from app.models.workspace import JournalNote
from app.router.model_router import get_router
from app.schemas.journal import (
    JournalEntryCreate,
    JournalEntryRead,
    JournalEntryUpdate,
    TranscribeResponse,
)
from app.security.auth import current_user
from app.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/journal", tags=["journal"])


def _read(note: JournalNote) -> JournalEntryRead:
    return JournalEntryRead(
        id=note.id,
        body=note.body,
        mood=note.mood,
        tags=list(note.tags or []),
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _load_entry(entry_id: int, user: User, db: Session) -> JournalNote:
    note = db.get(JournalNote, entry_id)
    visible = note is not None and note.deleted_at is None
    owned = note is not None and note.user_id in (None, user.id)
    if not (visible and owned):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "journal entry not found")
    return note


@router.post("/entries", response_model=JournalEntryRead, status_code=status.HTTP_201_CREATED)
def create_entry(
    payload: JournalEntryCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> JournalEntryRead:
    note = JournalNote(
        user_id=user.id,
        body=payload.body,
        mood=payload.mood,
        tags=payload.tags,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return _read(note)


@router.get("/entries", response_model=list[JournalEntryRead])
def list_entries(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[JournalEntryRead]:
    notes = (
        db.query(JournalNote)
        .filter(
            JournalNote.deleted_at.is_(None),
            (JournalNote.user_id == user.id) | (JournalNote.user_id.is_(None)),
        )
        .order_by(JournalNote.created_at.desc(), JournalNote.id.desc())
        .all()
    )
    return [_read(note) for note in notes]


@router.get("/entries/{entry_id}", response_model=JournalEntryRead)
def get_entry(
    entry_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> JournalEntryRead:
    return _read(_load_entry(entry_id, user, db))


@router.patch("/entries/{entry_id}", response_model=JournalEntryRead)
def update_entry(
    entry_id: int,
    payload: JournalEntryUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> JournalEntryRead:
    note = _load_entry(entry_id, user, db)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(note, field, value)
    db.commit()
    db.refresh(note)
    return _read(note)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    # Soft delete: flag the row, keep it and its content recoverable, and drop it from lists.
    note = _load_entry(entry_id, user, db)
    note.deleted_at = utcnow()
    db.commit()

# Maps a model id prefix to the settings field holding that provider's key.
_PROVIDER_KEY = {
    "openai/": "openai_api_key",
    "anthropic/": "anthropic_api_key",
    "gemini/": "gemini_api_key",
}


def _has_key_for(model_id: str) -> bool:
    settings = get_settings()
    for prefix, field in _PROVIDER_KEY.items():
        if model_id.startswith(prefix):
            return bool(getattr(settings, field, ""))
    # Unknown provider prefix: let the call proceed and surface any provider error.
    return True


@router.post("/transcribe", response_model=TranscribeResponse)
def transcribe(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TranscribeResponse:
    content = file.file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty audio upload")

    model_id = get_router().model_for("transcription")
    if not _has_key_for(model_id):
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "transcription is not configured on this Brain",
        )

    try:
        import litellm

        # A named in memory buffer: the provider SDK needs a filename, nothing touches disk.
        buffer = io.BytesIO(content)
        buffer.name = file.filename or "audio.webm"
        response = litellm.transcription(model=model_id, file=buffer)
        text = getattr(response, "text", None)
        if text is None and isinstance(response, dict):
            text = response.get("text")
    except Exception as exc:  # noqa: BLE001  surface as a transcription failure
        logger.warning("transcription failed: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "transcription failed") from exc

    return TranscribeResponse(transcript=(text or "").strip())
