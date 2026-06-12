"""Models and Agents settings: list, remap (persists and reroutes), and add a key."""

import shutil
from pathlib import Path

import pytest

from app.router import model_router
from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}
SOURCE = Path(__file__).resolve().parents[1] / "config" / "models.yaml"


@pytest.fixture(autouse=True)
def _reset_router_cache():
    # Leave the shared router resolving the real config for the rest of the suite.
    yield
    model_router.get_router.cache_clear()


def _isolate_config(monkeypatch, tmp_path) -> Path:
    """Point the router at a throwaway copy so edits do not touch the repo config."""
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")
    target = tmp_path / "models.yaml"
    shutil.copy(SOURCE, target)
    monkeypatch.setattr(model_router, "CONFIG_PATH", target)
    model_router.get_router.cache_clear()
    return target


def test_list_keys_and_agents(client, seed_user, monkeypatch, tmp_path):
    _isolate_config(monkeypatch, tmp_path)
    response = client.get("/settings/models", headers=BEARER)
    assert response.status_code == 200
    body = response.json()

    keys = {entry["key"]: entry for entry in body["keys"]}
    assert "general" in keys
    assert keys["general"]["model"]
    assert keys["agentic_code"]["cost"]["tier"] == "high"

    agents = {agent["id"]: agent for agent in body["agents"]}
    assert set(agents) == {"research", "build", "dreaming", "triage", "journal"}
    assert agents["build"]["model_key"] == "agentic_code"
    assert agents["build"]["resolved_model"] == keys["agentic_code"]["model"]


def test_remap_persists_and_reroutes(client, seed_user, monkeypatch, tmp_path):
    _isolate_config(monkeypatch, tmp_path)
    response = client.patch(
        "/settings/models/keys/general",
        json={"model": "openai/gpt-4o-mini"},
        headers=BEARER,
    )
    assert response.status_code == 200
    assert response.json()["model"] == "openai/gpt-4o-mini"
    assert response.json()["cost"]["tier"] == "low"

    # The cached router resolves the new model id without a reload.
    assert model_router.get_router().model_for("general") == "openai/gpt-4o-mini"
    # And it survives a reload from disk.
    model_router.get_router.cache_clear()
    assert model_router.get_router().model_for("general") == "openai/gpt-4o-mini"


def test_remap_unknown_key_is_404(client, seed_user, monkeypatch, tmp_path):
    _isolate_config(monkeypatch, tmp_path)
    response = client.patch(
        "/settings/models/keys/nope",
        json={"model": "openai/gpt-4o"},
        headers=BEARER,
    )
    assert response.status_code == 404


def test_add_key(client, seed_user, monkeypatch, tmp_path):
    _isolate_config(monkeypatch, tmp_path)
    response = client.post(
        "/settings/models/keys",
        json={"key": "captioning", "model": "openai/gpt-4o", "max_tokens": 800},
        headers=BEARER,
    )
    assert response.status_code == 201
    assert response.json()["key"] == "captioning"
    assert model_router.get_router().model_for("captioning") == "openai/gpt-4o"

    # A duplicate key is rejected.
    dup = client.post(
        "/settings/models/keys",
        json={"key": "captioning", "model": "openai/gpt-4o"},
        headers=BEARER,
    )
    assert dup.status_code == 409


def test_invalid_model_id_rejected(client, seed_user, monkeypatch, tmp_path):
    _isolate_config(monkeypatch, tmp_path)
    response = client.patch(
        "/settings/models/keys/general",
        json={"model": "not-a-provider-id"},
        headers=BEARER,
    )
    assert response.status_code == 422
