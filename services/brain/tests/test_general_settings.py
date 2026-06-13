"""General workspace settings persistence."""

from app.settings import get_settings

BEARER = {"Authorization": "Bearer t"}


def _bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")


def test_general_defaults_and_patch(client, seed_user, db_session, monkeypatch):
    _bearer(monkeypatch)
    defaults = client.get("/settings/general", headers=BEARER)
    assert defaults.status_code == 200
    body = defaults.json()
    assert body["timezone"] == "America/New_York"
    assert body["appearance"] == "system"
    assert body["notifications"] is True

    patched = client.patch(
        "/settings/general",
        json={
            "general_instructions": "Always answer in plain US English.",
            "appearance": "dark",
            "notifications": False,
        },
        headers=BEARER,
    )
    assert patched.status_code == 200
    out = patched.json()
    assert out["general_instructions"] == "Always answer in plain US English."
    assert out["appearance"] == "dark"
    assert out["notifications"] is False

    # Persisted across reads.
    again = client.get("/settings/general", headers=BEARER).json()
    assert again["appearance"] == "dark"
    assert again["general_instructions"] == "Always answer in plain US English."
