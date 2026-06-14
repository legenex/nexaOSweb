"""Smart gates: recommended defaults and deny-by-default autonomy auto-resolve."""

import pytest

from app.gates import (
    SAFE_TAGS,
    UNSAFE_TAGS,
    can_auto_resolve,
    is_safe_set,
    materially_affects_outcome,
    recommend_gate,
)
from app.runtime import PLANNED, WAITING_APPROVAL, create_run, propose_step

SAFE_RISK = {"low_risk": True, "reversible": True, "local": True, "non_external": True}


def _payload(risk):
    return {"risk": risk}


def test_full_safe_set_auto_resolves_above_zero():
    assert can_auto_resolve(_payload(SAFE_RISK), autonomy_level=2) is True
    assert is_safe_set(_payload(SAFE_RISK)) is True


def test_autonomy_zero_never_auto_resolves_even_when_safe():
    assert can_auto_resolve(_payload(SAFE_RISK), autonomy_level=0) is False


def test_unclassified_is_unsafe():
    assert can_auto_resolve({}, autonomy_level=3) is False
    assert can_auto_resolve(None, autonomy_level=3) is False
    assert can_auto_resolve({"risk": {}}, autonomy_level=3) is False


@pytest.mark.parametrize("missing", SAFE_TAGS)
def test_missing_any_safe_tag_is_not_auto_resolved(missing):
    risk = {tag: True for tag in SAFE_TAGS if tag != missing}
    assert can_auto_resolve(_payload(risk), autonomy_level=3) is False


@pytest.mark.parametrize("unsafe", UNSAFE_TAGS)
def test_any_unsafe_tag_is_not_auto_resolved(unsafe):
    risk = {**SAFE_RISK, unsafe: True}
    assert can_auto_resolve(_payload(risk), autonomy_level=3) is False
    assert materially_affects_outcome(_payload(risk)) is True


def test_recommend_gate_framing():
    safe = recommend_gate_for_payload(_payload(SAFE_RISK))
    assert safe["recommended_default"] == "proceed"
    assert safe["materially_affects"] is False

    material = recommend_gate_for_payload(_payload({**SAFE_RISK, "destructive": True}))
    assert material["recommended_default"] == "change"
    assert material["materially_affects"] is True


def recommend_gate_for_payload(payload):
    # recommend_gate reads step.payload; a light stand-in keeps the test focused on the logic.
    from types import SimpleNamespace

    return recommend_gate(SimpleNamespace(payload=payload))


# --- integration with propose_step (the deny-by-default entry gate) ------------------------


def test_propose_step_auto_resolves_only_full_safe_set_above_zero(db_session):
    run = create_run(db_session, autonomy_level=2)
    safe = propose_step(db_session, run, title="safe local edit", payload=_payload(SAFE_RISK))
    assert safe.status == PLANNED


def test_propose_step_gates_unclassified_above_zero(db_session):
    run = create_run(db_session, autonomy_level=2)
    step = propose_step(db_session, run, title="unclassified", payload={})
    assert step.status == WAITING_APPROVAL


@pytest.mark.parametrize("unsafe", UNSAFE_TAGS)
def test_propose_step_gates_any_unsafe_tag(db_session, unsafe):
    run = create_run(db_session, autonomy_level=3)
    step = propose_step(
        db_session, run, title="risky", payload=_payload({**SAFE_RISK, unsafe: True})
    )
    assert step.status == WAITING_APPROVAL


def test_propose_step_autonomy_zero_gates_even_safe(db_session):
    run = create_run(db_session, autonomy_level=0)
    step = propose_step(db_session, run, title="safe but autonomy 0", payload=_payload(SAFE_RISK))
    assert step.status == WAITING_APPROVAL
