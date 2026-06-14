"""Secure credential request and fulfilment: secrets never enter the ledger or context."""

import json

from app.agents.context import inject_context
from app.agents.readiness import (
    PENDING_STATUS,
    evaluate_readiness,
    readiness_satisfied,
    readiness_steps,
)
from app.models.project import Integration
from app.models.runtime import AgentRun, AgentStep
from app.runtime import WAITING_APPROVAL, create_run
from app.security.redaction import SecretLeakError, assert_no_secret, find_secret_fields
from app.security.secret_store import has_secret, secret_ref
from app.settings import get_settings

BEARER = {"Authorization": "Bearer t"}
SECRET = "sk_live_THE_ACTUAL_SECRET_VALUE"


def _bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")


def _isolate_secrets(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "nexa_secrets_root", str(tmp_path / "secrets"))


def _credential_plan():
    return {
        "requirements": [
            {
                "key": "credential:sendgrid",
                "question": "Connect SendGrid.",
                "kind": "credential",
                "provider": "sendgrid",
            }
        ]
    }


def _ledger_blob(db):
    """Every serialisable field of every run and step, for a leak scan."""
    parts = []
    for run in db.query(AgentRun).all():
        parts.append(
            json.dumps(
                {"plan": run.plan, "goal": run.goal_summary, "ctx": run.context_summary}
            )
        )
    for step in db.query(AgentStep).all():
        parts.append(
            json.dumps(
                {
                    "title": step.title,
                    "intent": step.intent,
                    "payload": step.payload,
                    "evidence": step.evidence,
                    "approval": step.approval,
                    "outcome": step.outcome,
                }
            )
        )
    return "\n".join(parts)


def test_request_path_parks_pending_integration_and_gates(db_session, seed_user):
    run = evaluate_readiness(db_session, plan=_credential_plan(), user_id=seed_user.id)

    integration = (
        db_session.query(Integration)
        .filter(Integration.user_id == seed_user.id, Integration.provider == "sendgrid")
        .one()
    )
    # A pending row with no secret material, only a provider and the pending status.
    assert integration.status == PENDING_STATUS
    assert integration.credentials_ref is None

    step = readiness_steps(db_session, run)[0]
    assert step.status == WAITING_APPROVAL
    rd = step.payload["readiness"]
    assert rd["resolution"] == "needs_credential"
    assert rd["integration_id"] == integration.id
    # The step records what is needed, never a value.
    assert find_secret_fields(step.payload) == []
    assert readiness_satisfied(db_session, run) is False


def test_unprovided_credential_keeps_readiness_blocked(db_session, seed_user):
    run = evaluate_readiness(db_session, plan=_credential_plan(), user_id=seed_user.id)
    assert readiness_satisfied(db_session, run) is False
    # Still blocked on a second look: the pending row is not treated as connected.
    again = evaluate_readiness(db_session, plan=_credential_plan(), user_id=seed_user.id)
    assert readiness_satisfied(db_session, again) is False


def test_fulfilment_connects_and_resolves_without_leaking(
    client, db_session, seed_user, monkeypatch, tmp_path
):
    _bearer(monkeypatch)
    _isolate_secrets(monkeypatch, tmp_path)

    run = evaluate_readiness(db_session, plan=_credential_plan(), user_id=seed_user.id)
    step = readiness_steps(db_session, run)[0]

    res = client.post(
        "/integrations/credentials/fulfil",
        json={"step_id": step.id, "secret": SECRET},
        headers=BEARER,
    )
    assert res.status_code == 200
    body = res.json()

    # The Integration is connected and carries only the reference, never the value.
    assert body["status"] == "connected"
    assert body["credentials_ref"] == secret_ref("sendgrid")
    assert SECRET not in res.text
    assert "secret" not in {k.lower() for k in body}  # no secret field on the read model

    # The secret lives only in the server side store.
    assert has_secret("sendgrid") is True

    # The Integration row in the database is connected by reference.
    integration = db_session.get(Integration, body["id"])
    db_session.refresh(integration)
    assert integration.status == "connected"
    assert integration.credentials_ref == secret_ref("sendgrid")

    # The readiness item is now resolved: no blocking item remains.
    db_session.refresh(run)
    assert readiness_satisfied(db_session, run) is True

    # The value is absent from every run and step field in the ledger.
    assert SECRET not in _ledger_blob(db_session)

    # And absent from the assembled agent context.
    agent_run = create_run(db_session, autonomy_level=1)
    summary = inject_context(db_session, agent_run)
    assert SECRET not in summary
    # The resolved answer is surfaced by reference only.
    assert secret_ref("sendgrid") in summary or "sendgrid" in summary.lower()


def test_fulfilment_rejects_a_non_credential_step(
    client, db_session, seed_user, monkeypatch, tmp_path
):
    _bearer(monkeypatch)
    _isolate_secrets(monkeypatch, tmp_path)
    # A plain readiness gap (needs_user), not a credential request.
    run = evaluate_readiness(
        db_session,
        plan={"requirements": [{"key": "scope", "question": "Scope?", "kind": "decision"}]},
        user_id=seed_user.id,
    )
    step = readiness_steps(db_session, run)[0]
    res = client.post(
        "/integrations/credentials/fulfil",
        json={"step_id": step.id, "secret": SECRET},
        headers=BEARER,
    )
    assert res.status_code == 404
    assert SECRET not in res.text


def test_redaction_guard_blocks_secret_bearing_fields():
    # A reference is allowed.
    assert_no_secret({"credentials_ref": "secret://stripe"})
    assert find_secret_fields({"credentials_ref": "secret://stripe", "provider": "stripe"}) == []

    # A raw secret bearing field is refused, however it is nested.
    assert find_secret_fields({"secret": "x"}) == ["secret"]
    assert find_secret_fields({"evidence": [{"api_key": "x"}]}) == ["evidence[0].api_key"]
    for leaky in ({"secret": SECRET}, {"payload": {"password": "p"}}, [{"token": "t"}]):
        try:
            assert_no_secret(leaky)
            raise AssertionError("expected SecretLeakError")
        except SecretLeakError:
            pass

    # An empty secret bearing field is not a leak (nothing to hide).
    assert find_secret_fields({"secret": ""}) == []
