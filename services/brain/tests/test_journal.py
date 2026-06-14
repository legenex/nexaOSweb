"""Journal transcribe endpoint."""

from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


def test_transcribe_returns_501_when_unconfigured(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    response = client.post(
        "/journal/transcribe",
        files={"file": ("voice-note.webm", b"fake-audio-bytes", "audio/webm")},
        headers=BEARER,
    )
    assert response.status_code == 501


def test_transcribe_returns_transcript_when_configured(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test")

    class FakeTranscription:
        text = "  hello from the microphone  "

    import litellm

    def fake_transcription(model, file, **kwargs):
        assert model == "openai/whisper-1"
        assert file.read() == b"fake-audio-bytes"
        # The router resolves the provider key (here from the environment) and passes it per call.
        assert kwargs["api_key"] == "sk-test"
        return FakeTranscription()

    monkeypatch.setattr(litellm, "transcription", fake_transcription)

    response = client.post(
        "/journal/transcribe",
        files={"file": ("voice-note.webm", b"fake-audio-bytes", "audio/webm")},
        headers=BEARER,
    )
    assert response.status_code == 200
    assert response.json()["transcript"] == "hello from the microphone"


def test_transcribe_rejects_empty_upload(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test")
    response = client.post(
        "/journal/transcribe",
        files={"file": ("empty.webm", b"", "audio/webm")},
        headers=BEARER,
    )
    assert response.status_code == 400
