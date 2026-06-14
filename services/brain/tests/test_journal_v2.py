"""Journal v2: topics, attachments, handwritten capture, and inbound ingestion."""

from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


# --- topics --------------------------------------------------------------------------------


def test_topics_group_entries_and_soft_delete_falls_back_to_untopiced(
    client, seed_user, monkeypatch
):
    _bearer(monkeypatch)
    topic = client.post("/journal/topics", json={"name": "Work"}, headers=BEARER)
    assert topic.status_code == 201
    tid = topic.json()["id"]

    entry = client.post(
        "/journal/entries", json={"body": "standup notes", "topic_id": tid}, headers=BEARER
    )
    assert entry.status_code == 201
    eid = entry.json()["id"]
    assert entry.json()["topic_id"] == tid

    # The topic groups the entry: a topic-filtered list returns only it.
    grouped = client.get(f"/journal/entries?topic_id={tid}", headers=BEARER).json()
    assert [n["id"] for n in grouped] == [eid]
    assert any(t["id"] == tid for t in client.get("/journal/topics", headers=BEARER).json())

    # Soft delete the topic: it leaves the list, the entry is kept and falls back to untopiced.
    deleted = client.delete(f"/journal/topics/{tid}", headers=BEARER)
    assert deleted.status_code == 204
    assert all(t["id"] != tid for t in client.get("/journal/topics", headers=BEARER).json())
    kept = client.get(f"/journal/entries/{eid}", headers=BEARER).json()
    assert kept["topic_id"] is None  # untopiced, never hard deleted

    # A deleted topic can no longer be assigned.
    assert (
        client.post(
            "/journal/entries", json={"body": "x", "topic_id": tid}, headers=BEARER
        ).status_code
        == 404
    )


# --- attachments ---------------------------------------------------------------------------


def test_attachment_stores_under_gated_root_and_lists(client, seed_user, monkeypatch, tmp_path):
    _bearer(monkeypatch)
    monkeypatch.setattr(get_settings(), "nexa_uploads_root", str(tmp_path / "uploads"))

    made = client.post("/journal/entries", json={"body": "with a photo"}, headers=BEARER)
    eid = made.json()["id"]
    files = {"file": ("note.png", b"\x89PNG-fake-bytes", "image/png")}
    created = client.post(f"/journal/entries/{eid}/attachments", files=files, headers=BEARER)
    assert created.status_code == 201
    att = created.json()
    assert att["kind"] == "image"
    assert att["original_name"] == "note.png"
    assert "path" not in att  # the read model never exposes the on disk path

    # The bytes are stored under the gated uploads root.
    upload_root = tmp_path / "uploads"
    written = [p for p in upload_root.rglob("*") if p.is_file()]
    assert any(p.read_bytes() == b"\x89PNG-fake-bytes" for p in written)
    assert all(str(p).startswith(str(upload_root)) for p in written)

    listed = client.get(f"/journal/entries/{eid}/attachments", headers=BEARER).json()
    assert [a["id"] for a in listed] == [att["id"]]

    # Soft delete: drops from the list, the file is kept on disk.
    assert client.delete(f"/journal/attachments/{att['id']}", headers=BEARER).status_code == 204
    assert client.get(f"/journal/entries/{eid}/attachments", headers=BEARER).json() == []
    assert any(p.is_file() for p in upload_root.rglob("*"))


# --- handwritten capture -------------------------------------------------------------------


def test_capture_returns_text_with_model_when_configured(client, seed_user, monkeypatch):
    _bearer(monkeypatch)
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test")

    import litellm

    def fake_completion(model, messages, **kwargs):
        return {"choices": [{"message": {"content": "the handwritten text"}}]}

    monkeypatch.setattr(litellm, "completion", fake_completion)

    files = {"file": ("page.jpg", b"image-bytes", "image/jpeg")}
    res = client.post("/journal/capture", files=files, headers=BEARER)
    assert res.status_code == 200
    body = res.json()
    assert body["text"] == "the handwritten text"
    assert body["model"]  # the resolved vision model id, never hardcoded


def test_capture_returns_501_without_vision_key(client, seed_user, monkeypatch):
    _bearer(monkeypatch)
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    files = {"file": ("page.jpg", b"image-bytes", "image/jpeg")}
    res = client.post("/journal/capture", files=files, headers=BEARER)
    assert res.status_code == 501


# --- inbound ingestion ---------------------------------------------------------------------


def test_ingest_creates_a_source_tagged_entry(client, seed_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "journal_ingest_tokens", "whatsapp:secrettok")
    res = client.post(
        "/journal/ingest",
        json={"source": "whatsapp", "token": "secrettok", "body": "a message from my phone"},
    )
    assert res.status_code == 201
    entry = res.json()
    assert entry["body"] == "a message from my phone"
    assert "source:whatsapp" in entry["tags"]
    # The token authenticates the source and never lands in the entry.
    assert "secrettok" not in str(entry)


def test_ingest_rejects_bad_token_and_unknown_source(client, seed_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "journal_ingest_tokens", "whatsapp:secrettok")
    bad_token = client.post(
        "/journal/ingest", json={"source": "whatsapp", "token": "wrong", "body": "x"}
    )
    assert bad_token.status_code == 401
    unknown = client.post(
        "/journal/ingest", json={"source": "ghost", "token": "secrettok", "body": "x"}
    )
    assert unknown.status_code == 401


def test_ingest_rejects_malformed_payload(client, seed_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "journal_ingest_tokens", "whatsapp:secrettok")
    missing_body = client.post(
        "/journal/ingest", json={"source": "whatsapp", "token": "secrettok"}
    )
    assert missing_body.status_code == 422
    empty_body = client.post(
        "/journal/ingest", json={"source": "whatsapp", "token": "secrettok", "body": ""}
    )
    assert empty_body.status_code == 422
