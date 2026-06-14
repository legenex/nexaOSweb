"""Model provider credentials and model discovery.

Connect a model provider by handing its API key once: the key goes straight to the Brain secret
store by reference and is never echoed back, logged, or written to the ledger. The store first
resolution in the model router then lets every AI feature run on that key with nothing in .env.
Discovery pulls the concrete models a connected provider offers and caches them, auto enabling the
models the semantic keys already reference.

Managing provider credentials is an owner or admin action, the same bar as managing users, because
these keys are server wide. Reading the provider list and the discovered models is open to any
authenticated user; neither read ever carries a secret.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.provider import DiscoveredModel, ProviderCredential
from app.models.user import User
from app.router import discovery, model_router
from app.routers.users import require_manager
from app.schemas.providers import (
    ConnectProviderRequest,
    DiscoveredModelRead,
    ProviderStatus,
    ToggleModelRequest,
)
from app.security.auth import current_user
from app.security.redaction import assert_no_secret
from app.security.secret_store import (
    delete_secret,
    has_secret,
    mask_hint,
    store_secret,
)

router = APIRouter(prefix="/settings/providers", tags=["settings", "providers"])


def _status_for(db: Session, provider: str) -> ProviderStatus:
    """Build the non secret status view for a provider, store first then environment."""
    provider = provider.strip().lower()
    row = (
        db.query(ProviderCredential)
        .filter(ProviderCredential.provider == provider)
        .first()
    )
    if has_secret(provider):
        source: str | None = "store"
    elif provider in model_router.KNOWN_PROVIDERS and model_router.has_provider_key(provider):
        source = "env"
    else:
        source = None
    connected = source is not None
    return ProviderStatus(
        provider=provider,
        status="connected" if connected else "available",
        connected=connected,
        source=source,
        hint=(row.hint if row and source == "store" else None),
    )


@router.get("", response_model=list[ProviderStatus])
def list_providers(
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ProviderStatus]:
    """Every known provider plus any extra provider already connected, with status and hint."""
    providers = list(model_router.KNOWN_PROVIDERS)
    for row in db.query(ProviderCredential).all():
        if row.provider not in providers:
            providers.append(row.provider)
    return [_status_for(db, provider) for provider in providers]


@router.post("/connect", response_model=ProviderStatus)
def connect_provider(
    payload: ConnectProviderRequest,
    _actor: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> ProviderStatus:
    """Connect a provider: write the key to the secret store by reference, keep a last four hint.

    The key is written only to the server side store. The row carries the reference and the hint,
    never the value, and the response is the non secret status view.
    """
    provider = payload.provider.strip().lower()
    # The value goes to the server side store only; we keep just the reference and a masked hint.
    ref = store_secret(provider, payload.api_key)
    hint = mask_hint(payload.api_key)

    row = (
        db.query(ProviderCredential)
        .filter(ProviderCredential.provider == provider)
        .first()
    )
    if row is None:
        row = ProviderCredential(provider=provider)
        db.add(row)
    row.status = "connected"
    row.credentials_ref = ref
    row.hint = hint
    db.commit()

    status = _status_for(db, provider)
    # Backstop: the status view must never carry secret material before it is returned.
    assert_no_secret(status.model_dump(), "provider connect response")
    return status


@router.post("/{provider}/disconnect", response_model=ProviderStatus)
def disconnect_provider(
    provider: str,
    _actor: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> ProviderStatus:
    """Disconnect a provider: clear the stored key and the row reference.

    The stored secret is removed and the row returns to available. A provider still configured
    through the server side .env reports connected by environment; this never touches .env.
    """
    provider = provider.strip().lower()
    row = (
        db.query(ProviderCredential)
        .filter(ProviderCredential.provider == provider)
        .first()
    )
    if row is not None:
        row.status = "available"
        row.credentials_ref = None
        row.hint = None
        db.commit()
    delete_secret(provider)
    return _status_for(db, provider)


@router.post("/{provider}/refresh", response_model=list[DiscoveredModelRead])
def refresh_models(
    provider: str,
    _actor: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> list[DiscoveredModel]:
    """Pull live models for a connected provider and cache them, auto enabling referenced models."""
    provider = provider.strip().lower()
    if not model_router.has_provider_key(provider):
        raise HTTPException(
            http_status.HTTP_409_CONFLICT, f"no key is connected for provider {provider}"
        )
    try:
        return discovery.refresh_provider_models(db, provider)
    except discovery.DiscoveryError as exc:
        raise HTTPException(http_status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.get("/models", response_model=list[DiscoveredModelRead])
def list_discovered_models(
    provider: str | None = Query(default=None),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[DiscoveredModel]:
    return discovery.list_models(db, provider)


@router.patch("/models/{model_id}", response_model=DiscoveredModelRead)
def toggle_model(
    model_id: int,
    payload: ToggleModelRequest,
    _actor: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> DiscoveredModel:
    row = db.get(DiscoveredModel, model_id)
    if row is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "discovered model not found")
    row.enabled = payload.enabled
    db.commit()
    db.refresh(row)
    return row
