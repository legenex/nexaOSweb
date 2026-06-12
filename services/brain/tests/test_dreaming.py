"""Dreaming consolidation and the memory candidate review queue."""

from app.agents.dreaming import run_dream
from app.models.dreaming import MemoryCandidate
from app.models.inbox import InboxItem
from app.models.workspace import JournalNote
from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


def _fake_synth(key, prompt, schema):
    # Records nothing, returns a fixed candidate so endpoint tests are deterministic.
    return {
        "facet": "about_user",
        "kind": "preference",
        "scope": "personal",
        "content": "Prefers working in the early morning",
        "confidence": 0.8,
    }


def _seed_day(db, user):
    db.add(JournalNote(user_id=user.id, body="Felt most focused working in the early morning."))
    db.add(
        InboxItem(
            user_id=user.id,
            name="Build a landing page",
            body="for the new product",
            source="note",
            status="captured",
            stage_history=[],
        )
    )
    db.commit()


def test_extraction_uses_the_bulk_key(db_session, seed_user):
    _seed_day(db_session, seed_user)
    seen_keys: list[str] = []

    def recording_synth(key, prompt, schema):
        seen_keys.append(key)
        return _fake_synth(key, prompt, schema)

    run = run_dream(db_session, synthesize=recording_synth)

    assert run.status == "completed"
    assert run.items_considered == 2
    assert run.candidates_created == 2
    assert run.model_key == "bulk"
    assert seen_keys == ["bulk", "bulk"]


def test_offline_run_produces_candidates_without_a_provider_key(db_session, seed_user):
    # No provider key and no injected completion means the offline fallback runs.
    from app.router import model_router

    model_router._completion_fn = None
    _seed_day(db_session, seed_user)

    run = run_dream(db_session)

    assert run.candidates_created == 2
    candidates = db_session.query(MemoryCandidate).all()
    assert all(candidate.content for candidate in candidates)
    assert all(candidate.status == "pending" for candidate in candidates)


def test_manual_run_accept_promotes_and_dismiss_marks(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    monkeypatch.setattr("app.agents.dreaming.synthesize_json", _fake_synth)
    _seed_day(db_session, seed_user)

    run = client.post("/dreaming/run", headers=BEARER)
    assert run.status_code == 201
    assert run.json()["candidates_created"] == 2

    pending = client.get("/dreaming/candidates?status=pending", headers=BEARER).json()
    assert len(pending) == 2
    first, second = pending[0]["id"], pending[1]["id"]

    accepted = client.post(f"/dreaming/candidates/{first}/accept", headers=BEARER)
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["source"] == "dreaming"
    assert body["status"] == "active"
    assert body["provenance"]["candidate_id"] == first

    promoted = client.get("/knowledge?source=dreaming", headers=BEARER).json()
    assert any(entry["content"] == body["content"] for entry in promoted)

    # Accepting again is a conflict, the candidate already left the queue.
    again = client.post(f"/dreaming/candidates/{first}/accept", headers=BEARER)
    assert again.status_code == 409

    dismissed = client.post(f"/dreaming/candidates/{second}/dismiss", headers=BEARER)
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    runs = client.get("/dreaming/runs", headers=BEARER).json()
    assert len(runs) == 1
    assert runs[0]["trigger"] == "manual"
    assert runs[0]["status"] == "completed"


def test_accept_missing_candidate_is_404(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    missing = client.post("/dreaming/candidates/999999/accept", headers=BEARER)
    assert missing.status_code == 404
