"""System (Connection) settings: health view and a confirmed, hook guarded restart."""

import time

from app.routers import system
from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


def test_health_reports_status_and_components(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    response = client.get("/system/health", headers=BEARER)
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "ok"
    assert body["version"]
    assert body["process"]["pid"] > 0
    assert body["process"]["uptime_seconds"] >= 0
    assert "dialect" in body["database"]
    # The masked url never leaks a password.
    assert "***" not in body["database"]["url"] or "@" in body["database"]["url"]
    assert "up_to_date" in body["migration"]


def test_restart_requires_confirm(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    fired = {"count": 0}
    monkeypatch.setattr(system, "_restart_hook", lambda: fired.__setitem__("count", 1))

    # Without confirm the restart is refused and nothing is scheduled.
    refused = client.post("/system/restart", json={"confirm": False}, headers=BEARER)
    assert refused.status_code == 400
    assert fired["count"] == 0


def test_restart_schedules_when_confirmed(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    fired = {"count": 0}
    # Guard: replace the real exec so pytest is never re-executed, and shorten the delay.
    monkeypatch.setattr(system, "_restart_hook", lambda: fired.__setitem__("count", 1))
    monkeypatch.setattr(system, "RESTART_DELAY_SECONDS", 0.02)

    response = client.post("/system/restart", json={"confirm": True}, headers=BEARER)
    assert response.status_code == 200
    assert response.json()["scheduled"] is True

    # The timer fires shortly after the response is returned.
    deadline = time.time() + 1.0
    while fired["count"] == 0 and time.time() < deadline:
        time.sleep(0.01)
    assert fired["count"] == 1
