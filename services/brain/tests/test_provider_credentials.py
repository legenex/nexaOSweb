"""Provider credentials and model discovery.

Connecting a provider writes the key only to the server side store by reference; the response and
the logs never carry the value. Store first resolution then lets the router run on that key with
nothing in .env. Discovery caches live models additively and auto enables the ones the semantic
keys reference. Managing providers is an owner or admin action.
"""

import json
import logging
from types import SimpleNamespace

from app.router import discovery, model_router
from app.router.model_router import get_router
from app.security.redaction import ALLOWED_REFERENCE_FIELDS, SECRET_FIELD_NAMES
from app.security.secret_store import has_secret, read_secret, secret_ref
from app.settings import get_settings

BEARER = {"Authorization": "Bearer t"}
KEY = "sk-ant-THE_ACTUAL_PROVIDER_KEY_VALUE_1234"


def _bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")


def _isolate_secrets(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "nexa_secrets_root", str(tmp_path / "secrets"))


def _clear_provider_env(monkeypatch):
    """No provider keys in the environment, so resolution is exercised store first only."""
    for field in model_router.PROVIDER_ENV_FIELDS.values():
        monkeypatch.setattr(get_settings(), field, "")


# --- connect: secret goes to the store, never returned or logged -------------------------------


def test_connect_stores_key_by_reference_and_never_returns_it(
    client, seed_user, db_session, monkeypatch, tmp_path, caplog
):
    _bearer(monkeypatch)
    _isolate_secrets(monkeypatch, tmp_path)

    with caplog.at_level(logging.DEBUG):
        res = client.post(
            "/settings/providers/connect",
            json={"provider": "anthropic", "api_key": KEY},
            headers=BEARER,
        )
    assert res.status_code == 200
    body = res.json()

    # The response is the non secret status view: connected, with a last four hint, no value.
    assert body["provider"] == "anthropic"
    assert body["status"] == "connected"
    assert body["connected"] is True
    assert body["source"] == "store"
    assert body["hint"] == "****1234"
    assert KEY not in res.text
    assert "api_key" not in {k.lower() for k in body}
    assert "secret" not in {k.lower() for k in body}

    # The key is absent from the logs.
    assert KEY not in caplog.text

    # The value lives only in the server side store, reachable by the sanctioned server read.
    assert has_secret("anthropic") is True
    assert read_secret("anthropic") == KEY


def test_connect_requires_owner_or_admin(client, seed_user):
    # A logged in member may not manage provider credentials: the manage gate returns 403.
    assert seed_user.role == "member"
    login = client.post(
        "/auth/login", json={"email": "nick@example.com", "password": "correct horse"}
    )
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    res = client.post(
        "/settings/providers/connect",
        json={"provider": "anthropic", "api_key": KEY},
        headers={"X-CSRF-Token": csrf},
    )
    assert res.status_code == 403


def test_connect_rejects_anonymous(client, seed_user):
    res = client.post(
        "/settings/providers/connect", json={"provider": "anthropic", "api_key": KEY}
    )
    assert res.status_code == 401


def test_no_route_exposes_a_planted_key(client, seed_user, monkeypatch, tmp_path):
    """A connected key never appears in the OpenAPI document or in any read response.

    read_secret and resolve_provider_key return the raw key but are server side only: no route is
    wired to them and no response model declares a secret bearing field. This greps the live OpenAPI
    schema and every provider read body for the planted literal and asserts it is absent, the
    structural proof that neither helper is reachable over HTTP.
    """
    _bearer(monkeypatch)
    _isolate_secrets(monkeypatch, tmp_path)
    _clear_provider_env(monkeypatch)

    # Connect and discover, so a real key is stored and discovered rows exist to serialise.
    client.post(
        "/settings/providers/connect",
        json={"provider": "anthropic", "api_key": KEY},
        headers=BEARER,
    )
    _fake_lister(monkeypatch, ["claude-sonnet-4-6", "claude-3-opus-latest"])
    client.post("/settings/providers/anthropic/refresh", headers=BEARER)

    # The key resolves server side (proving it is stored), so the grep below is meaningful.
    assert model_router.resolve_provider_key("anthropic") == KEY

    # The OpenAPI document never carries the planted key, and no provider response schema declares a
    # secret bearing field name (only a reference field is permitted).
    schema = client.get("/openapi.json").json()
    assert KEY not in json.dumps(schema)
    components = schema.get("components", {}).get("schemas", {})
    for name in ("ProviderStatus", "DiscoveredModelRead"):
        props = components.get(name, {}).get("properties", {})
        offending = {
            field
            for field in props
            if field.lower() in SECRET_FIELD_NAMES
            and field.lower() not in ALLOWED_REFERENCE_FIELDS
        }
        assert not offending, f"{name} exposes secret bearing field(s): {offending}"

    # Every provider read endpoint, and the connect response, return the key nowhere.
    reads = [
        client.post(
            "/settings/providers/connect",
            json={"provider": "anthropic", "api_key": KEY},
            headers=BEARER,
        ),
        client.get("/settings/providers", headers=BEARER),
        client.get(
            "/settings/providers/models", params={"provider": "anthropic"}, headers=BEARER
        ),
    ]
    for res in reads:
        assert res.status_code == 200
        assert KEY not in res.text


# --- store first resolution lets every feature run on the connected key ------------------------


def test_store_first_resolution_passes_key_to_litellm(
    client, seed_user, monkeypatch, tmp_path
):
    _bearer(monkeypatch)
    _isolate_secrets(monkeypatch, tmp_path)
    _clear_provider_env(monkeypatch)

    # Nothing connected and nothing in .env: no key resolves.
    assert model_router.resolve_provider_key("anthropic") is None
    assert model_router.has_provider_key("anthropic") is False

    res = client.post(
        "/settings/providers/connect",
        json={"provider": "anthropic", "api_key": KEY},
        headers=BEARER,
    )
    assert res.status_code == 200

    # Now the key resolves from the store, with nothing in .env.
    assert model_router.resolve_provider_key("anthropic") == KEY
    assert model_router.has_provider_key("anthropic") is True

    # And the router hands it to litellm per call (general maps to an anthropic model).
    captured = {}

    def fake_completion(model, messages, **params):
        captured.update(params)
        captured["model"] = model
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )

    monkeypatch.setattr(model_router, "_completion_fn", fake_completion)
    try:
        get_router().route_completion("general", [{"role": "user", "content": "hi"}])
    finally:
        monkeypatch.setattr(model_router, "_completion_fn", None)
    assert captured["api_key"] == KEY
    assert captured["model"].startswith("anthropic/")


def test_env_key_is_used_when_no_provider_connected(monkeypatch, tmp_path):
    _isolate_secrets(monkeypatch, tmp_path)
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr(get_settings(), "openai_api_key", "env-openai-key")
    # No connected secret, so the environment is the fallback.
    assert model_router.resolve_provider_key("openai") == "env-openai-key"
    assert model_router.has_provider_key("openai") is True


# --- discovery: live models cached additively, referenced ones auto enabled --------------------


def _fake_lister(monkeypatch, models):
    monkeypatch.setattr(discovery, "_list_models_fn", lambda provider, api_key: list(models))


def test_discovery_caches_models_and_auto_enables_referenced(
    client, seed_user, monkeypatch, tmp_path
):
    _bearer(monkeypatch)
    _isolate_secrets(monkeypatch, tmp_path)
    _clear_provider_env(monkeypatch)

    client.post(
        "/settings/providers/connect",
        json={"provider": "anthropic", "api_key": KEY},
        headers=BEARER,
    )

    # claude-sonnet-4-6 is referenced by the general key; the others are not.
    _fake_lister(
        monkeypatch,
        ["claude-sonnet-4-6", "claude-3-5-haiku-latest", "claude-3-opus-latest"],
    )

    res = client.post("/settings/providers/anthropic/refresh", headers=BEARER)
    assert res.status_code == 200
    models = {m["model_id"]: m for m in res.json()}

    assert "anthropic/claude-sonnet-4-6" in models
    # The referenced model is auto enabled; the others default to disabled.
    assert models["anthropic/claude-sonnet-4-6"]["enabled"] is True
    assert models["anthropic/claude-3-5-haiku-latest"]["enabled"] is False
    assert models["anthropic/claude-3-opus-latest"]["enabled"] is False

    # The cache is additive: a second refresh that drops a model keeps the earlier rows.
    _fake_lister(monkeypatch, ["claude-sonnet-4-6"])
    again = client.post("/settings/providers/anthropic/refresh", headers=BEARER).json()
    ids = {m["model_id"] for m in again}
    assert "anthropic/claude-3-opus-latest" in ids


def test_toggle_enable_persists(client, seed_user, monkeypatch, tmp_path):
    _bearer(monkeypatch)
    _isolate_secrets(monkeypatch, tmp_path)
    client.post(
        "/settings/providers/connect",
        json={"provider": "anthropic", "api_key": KEY},
        headers=BEARER,
    )
    _fake_lister(monkeypatch, ["claude-3-opus-latest"])
    rows = client.post("/settings/providers/anthropic/refresh", headers=BEARER).json()
    model_pk = rows[0]["id"]
    assert rows[0]["enabled"] is False

    enabled = client.patch(
        f"/settings/providers/models/{model_pk}", json={"enabled": True}, headers=BEARER
    )
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    listed = client.get(
        "/settings/providers/models", params={"provider": "anthropic"}, headers=BEARER
    ).json()
    assert listed[0]["enabled"] is True


def test_refresh_without_a_connected_key_is_a_conflict(
    client, seed_user, monkeypatch, tmp_path
):
    _bearer(monkeypatch)
    _isolate_secrets(monkeypatch, tmp_path)
    _clear_provider_env(monkeypatch)
    res = client.post("/settings/providers/openai/refresh", headers=BEARER)
    assert res.status_code == 409


# --- list and disconnect -----------------------------------------------------------------------


def test_list_providers_reports_status_and_hint(
    client, seed_user, monkeypatch, tmp_path
):
    _bearer(monkeypatch)
    _isolate_secrets(monkeypatch, tmp_path)
    _clear_provider_env(monkeypatch)
    client.post(
        "/settings/providers/connect",
        json={"provider": "anthropic", "api_key": KEY},
        headers=BEARER,
    )
    listed = client.get("/settings/providers", headers=BEARER).json()
    by_provider = {p["provider"]: p for p in listed}
    # Every known provider appears.
    for provider in model_router.KNOWN_PROVIDERS:
        assert provider in by_provider
    assert by_provider["anthropic"]["connected"] is True
    assert by_provider["anthropic"]["hint"] == "****1234"
    assert by_provider["openai"]["connected"] is False
    assert by_provider["openai"]["hint"] is None


def test_disconnect_clears_the_stored_key(client, seed_user, monkeypatch, tmp_path):
    _bearer(monkeypatch)
    _isolate_secrets(monkeypatch, tmp_path)
    _clear_provider_env(monkeypatch)
    client.post(
        "/settings/providers/connect",
        json={"provider": "anthropic", "api_key": KEY},
        headers=BEARER,
    )
    assert has_secret("anthropic") is True

    res = client.post("/settings/providers/anthropic/disconnect", headers=BEARER)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "available"
    assert body["connected"] is False
    assert body["hint"] is None

    # The stored secret is gone and the key no longer resolves.
    assert has_secret("anthropic") is False
    assert model_router.resolve_provider_key("anthropic") is None
    assert secret_ref("anthropic") == "secret://anthropic"
