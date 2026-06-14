"""Live model discovery for connected providers.

Discovery pulls the concrete models a connected provider offers and caches them additively in the
discovered_models table. Each cached row carries an enabled flag; the models the semantic keys in
config/models.yaml already reference are auto enabled, so the mapping the Brain actually uses is
selectable out of the box. Refresh never destroys a row or clobbers a user's enable choice: it
upserts, and a reference always wins (a referenced model stays enabled).

The provider list call is reached through an injectable so the rest of the system, and the tests,
never make a network call unless they mean to. The real fetcher talks to each provider's models
endpoint over HTTPS with the connected key, which is read server side and never returned.
"""

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.models.provider import DiscoveredModel
from app.router import model_router

logger = logging.getLogger(__name__)

# Injectable provider listing: (provider, api_key) -> list of raw model ids. Bound lazily to the
# real HTTPS fetcher; tests replace it so no network call is made.
_list_models_fn: Callable[[str, str], list[str]] | None = None


class DiscoveryError(Exception):
    """Raised when a provider's models cannot be listed (no key, or the call failed)."""


def _canonical_id(provider: str, raw_id: str) -> str:
    """The provider prefixed id, matching what config/models.yaml references."""
    raw = raw_id.strip()
    # Gemini returns names like models/gemini-1.5-pro; keep only the trailing id.
    if "/" in raw:
        raw = raw.split("/")[-1]
    return f"{provider}/{raw}"


def referenced_model_ids() -> set[str]:
    """The set of concrete model ids the semantic keys currently map to."""
    models = model_router.load_config().get("models", {})
    out: set[str] = set()
    for spec in models.values():
        model_id = str(spec.get("model", "")).strip()
        if model_id:
            out.add(model_id)
    return out


def _fetch_models(provider: str, api_key: str) -> list[str]:
    """Real provider listing over HTTPS. Returns raw model ids for the provider.

    The connected key is sent only to the provider's own models endpoint over TLS. Network and
    parse failures raise DiscoveryError so the caller can surface a clean error.
    """
    import httpx

    try:
        if provider == "openai":
            resp = httpx.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=20.0,
            )
            resp.raise_for_status()
            return [str(m.get("id", "")) for m in resp.json().get("data", []) if m.get("id")]
        if provider == "anthropic":
            resp = httpx.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                timeout=20.0,
            )
            resp.raise_for_status()
            return [str(m.get("id", "")) for m in resp.json().get("data", []) if m.get("id")]
        if provider == "gemini":
            resp = httpx.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
                timeout=20.0,
            )
            resp.raise_for_status()
            return [str(m.get("name", "")) for m in resp.json().get("models", []) if m.get("name")]
    except Exception as exc:  # noqa: BLE001  surface as a discovery failure, key never logged
        raise DiscoveryError(f"could not list models for {provider}") from exc
    raise DiscoveryError(f"discovery is not supported for provider {provider}")


def _list_models(provider: str, api_key: str) -> list[str]:
    fn = _list_models_fn or _fetch_models
    return fn(provider, api_key)


def refresh_provider_models(db: Session, provider: str) -> list[DiscoveredModel]:
    """Pull live models for a connected provider and cache them additively.

    Resolves the provider key store first (then environment) and lists the provider's models. Each
    id is upserted into discovered_models: a new row is enabled when a semantic key references it,
    an existing row keeps its enable choice but a referenced id is force enabled. Rows that the
    provider no longer returns are left in place (additive, never destroyed).
    """
    provider = provider.strip().lower()
    api_key = model_router.resolve_provider_key(provider)
    if not api_key:
        raise DiscoveryError(f"no key is connected for provider {provider}")

    raw_ids = _list_models(provider, api_key)
    referenced = referenced_model_ids()

    existing = {
        row.model_id: row
        for row in db.query(DiscoveredModel).filter(DiscoveredModel.provider == provider).all()
    }
    seen: set[str] = set()
    for raw_id in raw_ids:
        if not raw_id.strip():
            continue
        canonical = _canonical_id(provider, raw_id)
        if canonical in seen:
            continue
        seen.add(canonical)
        is_referenced = canonical in referenced
        row = existing.get(canonical)
        if row is None:
            row = DiscoveredModel(
                provider=provider,
                model_id=canonical,
                name=raw_id.strip().split("/")[-1],
                enabled=is_referenced,
            )
            db.add(row)
        elif is_referenced and not row.enabled:
            row.enabled = True
    db.commit()
    return list_models(db, provider)


def list_models(db: Session, provider: str | None = None) -> list[DiscoveredModel]:
    query = db.query(DiscoveredModel)
    if provider:
        query = query.filter(DiscoveredModel.provider == provider.strip().lower())
    return query.order_by(
        DiscoveredModel.provider.asc(), DiscoveredModel.model_id.asc()
    ).all()
