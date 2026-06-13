"""Journal endpoints.

Voice capture transcription. The uploaded audio is transcribed through the transcription model
key resolved by the router (never a hardcoded model id) and the transcript text is returned.
The audio is processed in memory and never written to disk, consistent with the journal image
rule. When no provider key backs the transcription model the route returns 501 Not Implemented
so the client can distinguish a genuinely unconfigured Brain from a browser or upload failure.
"""

import io
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.router.model_router import get_router
from app.schemas.journal import TranscribeResponse
from app.security.auth import current_user
from app.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/journal", tags=["journal"])

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
