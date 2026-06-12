"""Router acceptance: every key resolves, and synthesize_json parses a mocked reply."""

from types import SimpleNamespace

from app.json_extract import synthesize_json
from app.router import model_router
from app.router.model_router import get_router

EXPECTED_KEYS = [
    "general",
    "agentic_code",
    "research_synthesis",
    "bulk",
    "journal_reflection",
    "vision",
]


def test_every_key_resolves_to_a_model():
    router = get_router()
    for key in EXPECTED_KEYS:
        model = router.model_for(key)
        assert isinstance(model, str)
        assert model


def test_sampling_is_normalized():
    router = get_router()
    params = router.params_for("general", temperature=5.0, top_p=2.0)
    assert params["temperature"] == 2.0
    assert params["top_p"] == 1.0


def test_synthesize_json_parses_structured_response(monkeypatch):
    captured = {}

    def fake_completion(model, messages, **params):
        captured["model"] = model
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"shape": "project", "confidence": 0.9}')
                )
            ]
        )

    monkeypatch.setattr(model_router, "_completion_fn", fake_completion)

    result = synthesize_json(
        "agentic_code",
        "classify this idea",
        schema={"type": "object", "properties": {"shape": {"type": "string"}}},
    )
    assert result == {"shape": "project", "confidence": 0.9}
    assert captured["model"] == get_router().model_for("agentic_code")


def test_parse_json_tolerates_prose_and_fences():
    from app.json_extract import parse_json

    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('here you go: {"a": 2} done') == {"a": 2}
