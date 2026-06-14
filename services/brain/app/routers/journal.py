"""Journal endpoints.

Entry CRUD plus topics, attachments, capture, and inbound ingestion, built on the v1 JournalNote.

Entries carry text, an optional mood and tags, an optional topic, and timestamps; they are soft
deleted (a deleted entry keeps its row and stays recoverable) and feed the nightly Dreaming
consolidation as an input, human gated, never auto-writing Knowledge.

Topics are user created groupings; soft deleting a topic falls its entries back to untopiced and
keeps them. Attachments store bytes under NEXA_UPLOADS_ROOT through the path safety gate, keeping
only a relative reference on the row. Voice transcription and handwritten capture resolve the
transcription and vision model keys through the router (never a hardcoded model id) and return 501
when no provider key backs the chosen model, so the client can tell a genuinely unconfigured Brain
from a failure. Inbound ingestion accepts JSON from an external source authenticated by a per
source token; the token authenticates the source and never enters an entry.
"""

import hmac
import io
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.base import utcnow
from app.models.user import User
from app.models.workspace import JournalAttachment, JournalNote, JournalTopic
from app.router import model_router
from app.router.model_router import get_router
from app.safety import PathSafetyError, safe_write_bytes
from app.schemas.journal import (
    AttachmentRead,
    CaptureResponse,
    IngestRequest,
    JournalEntryCreate,
    JournalEntryRead,
    JournalEntryUpdate,
    TopicCreate,
    TopicRead,
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
        topic_id=note.topic_id,
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


def _load_topic(topic_id: int, user: User, db: Session) -> JournalTopic:
    topic = db.get(JournalTopic, topic_id)
    visible = topic is not None and topic.deleted_at is None
    owned = topic is not None and topic.user_id in (None, user.id)
    if not (visible and owned):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "topic not found")
    return topic


# --- entries -------------------------------------------------------------------------------


@router.post("/entries", response_model=JournalEntryRead, status_code=status.HTTP_201_CREATED)
def create_entry(
    payload: JournalEntryCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> JournalEntryRead:
    if payload.topic_id is not None:
        _load_topic(payload.topic_id, user, db)  # the relationship is enforced here, not by a FK
    note = JournalNote(
        user_id=user.id,
        body=payload.body,
        mood=payload.mood,
        tags=payload.tags,
        topic_id=payload.topic_id,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return _read(note)


@router.get("/entries", response_model=list[JournalEntryRead])
def list_entries(
    topic_id: int | None = Query(None, description="filter to entries under this topic"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[JournalEntryRead]:
    query = db.query(JournalNote).filter(
        JournalNote.deleted_at.is_(None),
        (JournalNote.user_id == user.id) | (JournalNote.user_id.is_(None)),
    )
    if topic_id is not None:
        query = query.filter(JournalNote.topic_id == topic_id)
    notes = query.order_by(JournalNote.created_at.desc(), JournalNote.id.desc()).all()
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
    changes = payload.model_dump(exclude_none=True)
    if "topic_id" in changes:
        _load_topic(changes["topic_id"], user, db)
    for field, value in changes.items():
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


# --- topics --------------------------------------------------------------------------------


@router.post("/topics", response_model=TopicRead, status_code=status.HTTP_201_CREATED)
def create_topic(
    payload: TopicCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> JournalTopic:
    topic = JournalTopic(user_id=user.id, name=payload.name.strip())
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


@router.get("/topics", response_model=list[TopicRead])
def list_topics(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[JournalTopic]:
    return (
        db.query(JournalTopic)
        .filter(
            JournalTopic.deleted_at.is_(None),
            (JournalTopic.user_id == user.id) | (JournalTopic.user_id.is_(None)),
        )
        .order_by(JournalTopic.created_at.asc(), JournalTopic.id.asc())
        .all()
    )


@router.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic(
    topic_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    # Soft delete the topic, then fall its entries back to untopiced. The entries are never
    # hard deleted: only their topic_id is cleared so they keep showing under no topic.
    topic = _load_topic(topic_id, user, db)
    topic.deleted_at = utcnow()
    db.query(JournalNote).filter(JournalNote.topic_id == topic.id).update(
        {JournalNote.topic_id: None}, synchronize_session=False
    )
    db.commit()


# --- attachments ---------------------------------------------------------------------------


def _attachment_read(att: JournalAttachment) -> AttachmentRead:
    return AttachmentRead.model_validate(att)


@router.post(
    "/entries/{entry_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
def attach_to_entry(
    entry_id: int,
    file: UploadFile = File(...),
    kind: str | None = Form(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AttachmentRead:
    note = _load_entry(entry_id, user, db)
    content = file.file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty attachment upload")

    content_type = file.content_type or ""
    resolved_kind = (kind or ("image" if content_type.startswith("image/") else "file")).lower()
    if resolved_kind not in ("image", "file"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "kind must be image or file")

    original_name = file.filename or "attachment"
    # A unique relative path under the uploads root; the original name is kept on the row only.
    suffix = ("." + original_name.rsplit(".", 1)[-1]) if "." in original_name else ""
    relative = f"journal/{note.id}/{uuid.uuid4().hex}{suffix}"
    settings = get_settings()
    try:
        safe_write_bytes(settings.nexa_uploads_root, relative, content)
    except PathSafetyError as exc:  # pragma: no cover - relative is server generated
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid attachment path") from exc

    attachment = JournalAttachment(
        note_id=note.id,
        kind=resolved_kind,
        path=relative,
        original_name=original_name,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return _attachment_read(attachment)


@router.get("/entries/{entry_id}/attachments", response_model=list[AttachmentRead])
def list_attachments(
    entry_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[AttachmentRead]:
    _load_entry(entry_id, user, db)
    attachments = (
        db.query(JournalAttachment)
        .filter(
            JournalAttachment.note_id == entry_id,
            JournalAttachment.deleted_at.is_(None),
        )
        .order_by(JournalAttachment.created_at.asc(), JournalAttachment.id.asc())
        .all()
    )
    return [_attachment_read(att) for att in attachments]


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    attachment = db.get(JournalAttachment, attachment_id)
    if attachment is None or attachment.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "attachment not found")
    _load_entry(attachment.note_id, user, db)  # ownership via the parent entry
    # Soft delete: flag the row, keep it and its file recoverable, and drop it from lists.
    attachment.deleted_at = utcnow()
    db.commit()


# --- transcription and capture -------------------------------------------------------------


def _has_key_for(model_id: str) -> bool:
    """Whether a key is available for the model's provider, connected store first then environment.

    A model id with no known provider prefix is allowed through so any provider error surfaces from
    the call rather than being pre empted here.
    """
    provider = model_router.provider_of(model_id)
    if provider in model_router.KNOWN_PROVIDERS:
        return model_router.has_provider_key(provider)
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
        # Resolve the provider key store first, then environment, and pass it per call.
        api_key = model_router.resolve_provider_key(model_router.provider_of(model_id))
        kwargs = {"api_key": api_key} if api_key else {}
        response = litellm.transcription(model=model_id, file=buffer, **kwargs)
        text = getattr(response, "text", None)
        if text is None and isinstance(response, dict):
            text = response.get("text")
    except Exception as exc:  # noqa: BLE001  surface as a transcription failure
        logger.warning("transcription failed: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "transcription failed") from exc

    return TranscribeResponse(transcript=(text or "").strip())


def _vision_text(response: object) -> str:
    """Pull the assistant text out of a litellm completion response, defensively."""
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    if not choices:
        return ""
    first = choices[0]
    message = getattr(first, "message", None)
    if message is None and isinstance(first, dict):
        message = first.get("message")
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    return str(content or "").strip()


@router.post("/capture", response_model=CaptureResponse)
def capture(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CaptureResponse:
    """Transcribe a photo of a handwritten page via the vision model, returning the text.

    The image is processed in memory and never written to disk, consistent with the journal image
    rule. The returned text becomes an entry body or an attachment note, at the client's choice.
    When no provider key backs the vision model the route returns 501, never a stub.
    """
    content = file.file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty image upload")

    model_id = get_router().model_for("vision")
    if not _has_key_for(model_id):
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "handwriting capture is not configured on this Brain",
        )

    import base64

    content_type = file.content_type or "image/png"
    data_uri = f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}"
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Transcribe the handwritten text in this image exactly. Return only the "
                        "transcription, with no commentary."
                    ),
                },
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }
    ]
    try:
        import litellm

        # Resolve the provider key store first, then environment, and pass it per call.
        api_key = model_router.resolve_provider_key(model_router.provider_of(model_id))
        kwargs = {"api_key": api_key} if api_key else {}
        response = litellm.completion(model=model_id, messages=messages, **kwargs)
        text = _vision_text(response)
    except Exception as exc:  # noqa: BLE001  surface as a capture failure
        logger.warning("handwriting capture failed: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "handwriting capture failed") from exc

    return CaptureResponse(text=text, model=model_id)


# --- inbound ingestion ---------------------------------------------------------------------


@router.post("/ingest", response_model=JournalEntryRead, status_code=status.HTTP_201_CREATED)
def ingest(
    payload: IngestRequest,
    db: Session = Depends(get_db),
) -> JournalEntryRead:
    """Accept a journal entry from an external source, authenticated by a per source token.

    This route is machine to machine, not session authenticated: the per source token is the
    credential. The token is validated against the server side token map, then discarded; it never
    enters the entry. A malformed payload is rejected by the schema; an unknown source or a wrong
    token is a 401. The created entry is tagged with its source so the origin stays traceable.
    """
    token_map = get_settings().journal_ingest_token_map
    expected = token_map.get(payload.source)
    if not expected or not hmac.compare_digest(expected, payload.token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid source or token")

    # Attach to the owner (earliest user) so the entry lands in the single user's journal.
    owner = db.query(User).order_by(User.id.asc()).first()

    source_tag = f"source:{payload.source}"
    tags = list(payload.tags)
    if source_tag not in tags:
        tags.append(source_tag)

    note = JournalNote(
        user_id=owner.id if owner else None,
        body=payload.body,
        mood=payload.mood,
        tags=tags,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return _read(note)
