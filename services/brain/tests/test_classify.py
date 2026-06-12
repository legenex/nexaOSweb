"""Classifier and decision record."""

from app.agents.classify import classify_item, run_retry_sweep
from app.models.inbox import ClassificationRecord, InboxItem
from app.models.user import User
from app.settings import get_settings


def _make_item(db_session, name="Build a launch site", body="a multi step initiative"):
    user = db_session.query(User).first()
    if user is None:
        user = User(email="c@example.com", password_hash="x")
        db_session.add(user)
        db_session.flush()
    item = InboxItem(
        user_id=user.id, name=name, body=body, status="captured", stage_history=[]
    )
    db_session.add(item)
    db_session.flush()
    return item


def _fake(result):
    def synth(key, prompt, schema=None):
        return result

    return synth


def test_classify_persists_decision_record(db_session):
    item = _make_item(db_session)
    record = classify_item(
        db_session,
        item,
        synthesize=_fake(
            {
                "shape": "project",
                "confidence": 0.92,
                "tags": ["web", "launch"],
                "reasoning_summary": "Reads like a multi step build.",
            }
        ),
    )
    assert record.shape == "project"
    assert record.recommended_route == "project"
    assert record.recommended_model_key == "agentic_code"
    assert record.resolved_model_id
    assert "agentic_code" in record.model_rationale
    assert item.status == "classified"
    assert item.stage_history[-1]["stage"] == "classify"


def test_low_confidence_escalates(db_session):
    item = _make_item(db_session)
    classify_item(
        db_session,
        item,
        synthesize=_fake({"shape": "gtd", "confidence": 0.1, "reasoning_summary": "weak"}),
    )
    assert item.status == "escalated"


def test_invalid_shape_falls_back_to_park(db_session):
    item = _make_item(db_session)
    record = classify_item(
        db_session,
        item,
        synthesize=_fake({"shape": "nonsense", "confidence": 0.8, "reasoning_summary": "x"}),
    )
    assert record.shape == "park"
    assert record.recommended_route == "park"


def test_retry_sweep_processes_captured(db_session, monkeypatch):
    _make_item(db_session, name="one")
    _make_item(db_session, name="two")
    db_session.commit()

    import app.agents.classify as classify_mod

    monkeypatch.setattr(
        classify_mod,
        "synthesize_json",
        _fake({"shape": "park", "confidence": 0.9, "reasoning_summary": "later"}),
    )
    processed = run_retry_sweep(db_session, batch=10)
    assert processed == 2


def test_classification_endpoint(client, seed_user, db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    headers = {"Authorization": "Bearer t"}

    item = InboxItem(user_id=seed_user.id, name="x", status="captured", stage_history=[])
    db_session.add(item)
    db_session.flush()
    db_session.add(
        ClassificationRecord(
            item_id=item.id,
            shape="project",
            confidence=0.9,
            recommended_route="project",
            recommended_model_key="agentic_code",
            resolved_model_id="anthropic/claude-opus-4-8",
            model_rationale="r",
            reasoning_summary="s",
            tags=[],
        )
    )
    db_session.commit()

    found = client.get(f"/intake/items/{item.id}/classification", headers=headers)
    assert found.status_code == 200
    assert found.json()["shape"] == "project"

    bare = InboxItem(user_id=seed_user.id, name="y", status="captured", stage_history=[])
    db_session.add(bare)
    db_session.commit()
    missing = client.get(f"/intake/items/{bare.id}/classification", headers=headers)
    assert missing.status_code == 404
