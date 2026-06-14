"""Journal entry CRUD, soft delete, and the Dreaming input."""

from app.agents.dreaming import run_dream
from app.models.workspace import JournalNote
from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


def test_entries_round_trip(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    created = client.post(
        "/journal/entries",
        json={"body": "Felt focused this morning.", "mood": "focused", "tags": ["energy"]},
        headers=BEARER,
    )
    assert created.status_code == 201
    entry = created.json()
    assert entry["mood"] == "focused"
    assert entry["tags"] == ["energy"]

    fetched = client.get(f"/journal/entries/{entry['id']}", headers=BEARER).json()
    assert fetched["body"] == "Felt focused this morning."

    patched = client.patch(
        f"/journal/entries/{entry['id']}",
        json={"mood": "calm", "body": "Edited."},
        headers=BEARER,
    )
    assert patched.status_code == 200
    assert patched.json()["mood"] == "calm"
    assert patched.json()["body"] == "Edited."

    listed = client.get("/journal/entries", headers=BEARER).json()
    assert any(e["id"] == entry["id"] for e in listed)


def test_soft_delete_hides_but_keeps_recoverable(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    entry_id = client.post(
        "/journal/entries", json={"body": "to remove"}, headers=BEARER
    ).json()["id"]

    deleted = client.delete(f"/journal/entries/{entry_id}", headers=BEARER)
    assert deleted.status_code == 204

    # Hidden from the list and 404 on access,
    assert all(e["id"] != entry_id for e in client.get("/journal/entries", headers=BEARER).json())
    assert client.get(f"/journal/entries/{entry_id}", headers=BEARER).status_code == 404
    # but the row is preserved with a deleted marker, so it stays recoverable.
    row = db_session.get(JournalNote, entry_id)
    assert row is not None
    assert row.deleted_at is not None


def test_journal_feeds_dreaming_but_excludes_deleted(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    kept = client.post("/journal/entries", json={"body": "kept entry"}, headers=BEARER).json()["id"]
    gone = client.post("/journal/entries", json={"body": "gone entry"}, headers=BEARER).json()["id"]
    client.delete(f"/journal/entries/{gone}", headers=BEARER)

    # The Dreaming consolidation reads journal entries as a signal, minus soft deleted ones.
    seen: list[str] = []

    def fake_synth(key, prompt, schema, **_):
        seen.append(prompt)
        return {
            "facet": "about_user",
            "kind": "preference",
            "scope": "personal",
            "content": "x",
            "confidence": 0.7,
        }

    run = run_dream(db_session, synthesize=fake_synth)
    assert run.status == "completed"
    joined = "\n".join(seen)
    assert "kept entry" in joined
    assert "gone entry" not in joined
    assert kept  # referenced so the kept id is meaningful
