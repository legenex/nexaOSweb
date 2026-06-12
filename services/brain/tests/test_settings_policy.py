"""Knowledge policy settings: defaults, persistence, and the confidence bound."""

from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


def test_policy_defaults_keep_the_human_gate(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    response = client.get("/settings/knowledge-policy", headers=BEARER)
    assert response.status_code == 200
    body = response.json()
    assert body["memory_require_approval"] is True
    assert body["memory_allow_connectors"] is False
    assert body["ingest_chatgpt_api"] is False
    assert body["memory_min_confidence"] == 0.6


def test_policy_patch_persists(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    patched = client.patch(
        "/settings/knowledge-policy",
        json={"ingest_chatgpt_api": True, "memory_min_confidence": 0.8},
        headers=BEARER,
    )
    assert patched.status_code == 200
    assert patched.json()["ingest_chatgpt_api"] is True
    assert patched.json()["memory_min_confidence"] == 0.8

    # The change survives a fresh read, and untouched fields keep their defaults.
    again = client.get("/settings/knowledge-policy", headers=BEARER).json()
    assert again["ingest_chatgpt_api"] is True
    assert again["memory_min_confidence"] == 0.8
    assert again["memory_require_approval"] is True


def test_policy_rejects_out_of_range_confidence(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    response = client.patch(
        "/settings/knowledge-policy",
        json={"memory_min_confidence": 1.5},
        headers=BEARER,
    )
    assert response.status_code == 422
