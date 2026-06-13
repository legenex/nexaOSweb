"""Integrations connect/disconnect and the read only skills listing."""

from app.settings import get_settings

BEARER = {"Authorization": "Bearer t"}


def _bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")


def test_connect_list_disconnect(client, seed_user, db_session, monkeypatch):
    _bearer(monkeypatch)
    assert client.get("/integrations", headers=BEARER).json() == []

    connected = client.post("/integrations/connect", json={"provider": "Google"}, headers=BEARER)
    assert connected.status_code == 200
    row = connected.json()
    assert row["provider"] == "google"
    assert row["status"] == "connected"

    # Connecting again upserts the same row rather than duplicating.
    again = client.post("/integrations/connect", json={"provider": "google"}, headers=BEARER)
    assert again.json()["id"] == row["id"]
    assert len(client.get("/integrations", headers=BEARER).json()) == 1

    disconnected = client.post(f"/integrations/{row['id']}/disconnect", headers=BEARER)
    assert disconnected.status_code == 200
    assert disconnected.json()["status"] == "available"


def test_skills_lists_agents_and_connectors(client, seed_user, db_session, monkeypatch):
    _bearer(monkeypatch)
    client.post("/integrations/connect", json={"provider": "github"}, headers=BEARER)

    res = client.get("/skills", headers=BEARER)
    assert res.status_code == 200
    body = res.json()
    # Agents from config/models.yaml are surfaced as skills, resolved through the router.
    assert len(body["skills"]) > 0
    sample = body["skills"][0]
    assert sample["model_key"]
    assert "id" in sample and "label" in sample
    # Connector health reflects the connected integration.
    providers = {c["provider"] for c in body["connectors"]}
    assert "github" in providers
