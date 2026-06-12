"""Intake capture and item listing."""

from pathlib import Path

from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable_bearer(monkeypatch, uploads: Path):
    settings = get_settings()
    monkeypatch.setattr(settings, "nexa_desktop_bearer", "test-bearer")
    monkeypatch.setattr(settings, "nexa_uploads_root", str(uploads))


def test_capture_creates_item(client, seed_user, monkeypatch, tmp_path):
    _enable_bearer(monkeypatch, tmp_path)
    response = client.post(
        "/intake/capture",
        data={"name": "Make retries safer", "body": "background jobs", "source": "note"},
        headers=BEARER,
    )
    assert response.status_code == 201
    item = response.json()
    assert item["status"] == "captured"
    assert item["name"] == "Make retries safer"
    assert item["stage_history"][0]["stage"] == "capture"


def test_capture_stores_file_within_root(client, seed_user, monkeypatch, tmp_path):
    _enable_bearer(monkeypatch, tmp_path)
    response = client.post(
        "/intake/capture",
        data={"name": "With attachment"},
        files={"file": ("../evil notes.txt", b"payload", "text/plain")},
        headers=BEARER,
    )
    assert response.status_code == 201
    item_id = response.json()["id"]
    stored = list((tmp_path / "inbox" / str(item_id)).iterdir())
    assert len(stored) == 1
    # The traversal in the filename was stripped to a safe basename inside the root.
    assert stored[0].name == "evil_notes.txt"
    assert stored[0].read_bytes() == b"payload"


def test_list_and_get_items(client, seed_user, monkeypatch, tmp_path):
    _enable_bearer(monkeypatch, tmp_path)
    client.post("/intake/capture", data={"name": "One"}, headers=BEARER)
    created = client.post("/intake/capture", data={"name": "Two"}, headers=BEARER).json()

    page = client.get("/intake/items", headers=BEARER).json()
    assert page["total"] >= 2
    assert page["limit"] == 50

    one = client.get(f"/intake/items/{created['id']}", headers=BEARER)
    assert one.status_code == 200
    assert one.json()["name"] == "Two"

    missing = client.get("/intake/items/999999", headers=BEARER)
    assert missing.status_code == 404
