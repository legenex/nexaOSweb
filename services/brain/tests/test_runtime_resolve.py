"""The one human gate write: POST /runtime/steps/{id}/resolve."""

from app.runtime import create_run, propose_step
from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


def _gated_step(db_session):
    run = create_run(db_session, autonomy_level=0)
    return propose_step(db_session, run, title="risky", intent="do the risky thing")


def test_approve_moves_step_to_planned_and_out_of_queue(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    step = _gated_step(db_session)
    run_id = step.run_id

    response = client.post(
        f"/runtime/steps/{step.id}/resolve",
        json={"resolution": "approved", "note": "ok"},
        headers=BEARER,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "planned"
    assert response.json()["approval"]["resolution"] == "approved"

    queue = client.get(f"/runtime/runs/{run_id}/approvals", headers=BEARER).json()
    assert all(item["id"] != step.id for item in queue)


def test_reject_moves_step_to_skipped(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    step = _gated_step(db_session)
    response = client.post(
        f"/runtime/steps/{step.id}/resolve",
        json={"resolution": "rejected", "note": "no"},
        headers=BEARER,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "skipped"


def test_resolving_a_non_gated_step_is_conflict(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    # An auto-resolved safe step at higher autonomy is planned, not at the gate.
    run = create_run(db_session, autonomy_level=2)
    safe_risk = {"low_risk": True, "reversible": True, "local": True, "non_external": True}
    step = propose_step(db_session, run, title="safe", payload={"risk": safe_risk})
    assert step.status == "planned"

    response = client.post(
        f"/runtime/steps/{step.id}/resolve",
        json={"resolution": "approved"},
        headers=BEARER,
    )
    assert response.status_code == 409


def test_resolving_a_missing_step_is_404(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    response = client.post(
        "/runtime/steps/999999/resolve",
        json={"resolution": "approved"},
        headers=BEARER,
    )
    assert response.status_code == 404


def test_approvals_carry_recommended_default(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    step = _gated_step(db_session)
    queue = client.get(f"/runtime/runs/{step.run_id}/approvals", headers=BEARER).json()
    assert len(queue) == 1
    assert queue[0]["recommended_default"] in ("proceed", "change")
    assert "framing" in queue[0]
    assert isinstance(queue[0]["materially_affects"], bool)
