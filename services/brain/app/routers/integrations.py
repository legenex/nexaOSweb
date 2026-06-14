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

from app.agents.readiness import (
    CredentialRequestError,
    fulfil_credential_step,
    is_credential_request,
)
from app.db import get_db
from app.models.inbox import InboxItem
from app.models.project import Integration, Project
from app.models.runtime import AgentRun, AgentStep
from app.models.user import User
from app.schemas.entities import IntegrationRead
from app.schemas.integrations import ConnectRequest, FulfilCredentialRequest
from app.security.auth import current_user

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _user_owns_run(run: AgentRun, user: User, db: Session) -> bool:
    """A readiness run is the user's when it is unscoped or belongs to the user's project."""
    if run.project_id is None:
        return True
    project = db.get(Project, run.project_id)
    if project is None:
        return False
    if project.item_id is None:
        return True
    item = db.get(InboxItem, project.item_id)
    return item is not None and item.user_id == user.id


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


@router.post("/credentials/fulfil", response_model=IntegrationRead)
def fulfil_credential(
    payload: FulfilCredentialRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Integration:
    """Provide the secret for a pending credential request.

    The secret arrives over the authenticated session only, is written straight to the Brain
    secret store, flips the Integration to connected (by reference), and resolves the readiness
    step. The response is the integration read model, which carries the reference and never the
    value. The secret is never returned, logged, or written to the ledger.
    """
    step = db.get(AgentStep, payload.step_id)
    if step is None or not is_credential_request(step):
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "credential request not found")
    run = db.get(AgentRun, step.run_id)
    if run is None or not _user_owns_run(run, user, db):
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "credential request not found")
    try:
        return fulfil_credential_step(
            db,
            step=step,
            secret=payload.secret,
            user_id=user.id,
            resolved_by=user.email or "user",
        )
    except CredentialRequestError as exc:
        raise HTTPException(http_status.HTTP_409_CONFLICT, str(exc)) from exc


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
