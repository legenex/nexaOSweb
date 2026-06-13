"""Integrations: list, connect, and disconnect.

Operates over the integrations table, which records the providers a user has connected and a
reference to where credentials live (never the raw secret, per the secrets rule). connect
upserts a row to the connected status. For an OAuth provider such as Google, a real
authorization round trip needs server side client credentials in the Brain .env; until that
lands, connect marks the provider connected so the rest of the surface is exercised, and the
credentials_ref stays null. disconnect returns a provider to the available status.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.project import Integration
from app.models.user import User
from app.schemas.entities import IntegrationRead
from app.schemas.integrations import ConnectRequest
from app.security.auth import current_user

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationRead])
def list_integrations(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[Integration]:
    return (
        db.query(Integration)
        .filter(Integration.user_id == user.id)
        .order_by(Integration.provider.asc(), Integration.id.asc())
        .all()
    )


@router.post("/connect", response_model=IntegrationRead)
def connect(
    payload: ConnectRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Integration:
    provider = payload.provider.strip().lower()
    if not provider:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "a provider is required")
    row = (
        db.query(Integration)
        .filter(Integration.user_id == user.id, Integration.provider == provider)
        .first()
    )
    if row is None:
        row = Integration(user_id=user.id, provider=provider, status="connected")
        db.add(row)
    else:
        row.status = "connected"
    db.commit()
    db.refresh(row)
    return row


@router.post("/{integration_id}/disconnect", response_model=IntegrationRead)
def disconnect(
    integration_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Integration:
    row = db.get(Integration, integration_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "integration not found")
    row.status = "available"
    row.credentials_ref = None
    db.commit()
    db.refresh(row)
    return row
