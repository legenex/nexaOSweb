"""The Human Gate readiness endpoints: trigger an assessment and read it back."""

from app.models.inbox import InboxItem
from app.models.project import Project
from app.models.runtime import AgentStep
from app.runtime import WAITING_APPROVAL, resolve_approval
from app.settings import get_settings

BEARER = {"Authorization": "Bearer t"}


def _bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")


def _project(db_session):
    """An item plus its project, owned by the only (earliest) user the bearer acts as."""
    from app.models.user import User

    user = User(email="owner@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    item = InboxItem(user_id=user.id, name="Mailer", body="b", status="routed", stage_history=[])
    db_session.add(item)
    db_session.flush()
    project = Project(
        item_id=item.id,
        name="Mailer",
        slug="mailer",
        stage="clarify",
        plan_json={
            "requirements": [
                {"key": "decision:db", "question": "Which database?", "kind": "decision"}
            ]
        },
        selected_integrations=["sendgrid"],
    )
    db_session.add(project)
    db_session.commit()
    return item, project


def test_get_before_evaluate_is_unassessed(client, db_session, monkeypatch):
    _bearer(monkeypatch)
    item, _ = _project(db_session)
    res = client.get(f"/flow/items/{item.id}/readiness", headers=BEARER)
    # A never assessed project returns an unassessed result (run_id 0, not satisfied) rather
    # than a 404, so the gate panel reads it without a console error and stays closed.
    assert res.status_code == 200
    body = res.json()
    assert body["run_id"] == 0
    assert body["satisfied"] is False
    assert body["items"] == []


def test_evaluate_groups_by_class_and_gates(client, db_session, monkeypatch):
    _bearer(monkeypatch)
    item, _ = _project(db_session)

    posted = client.post(f"/flow/items/{item.id}/readiness", headers=BEARER)
    assert posted.status_code == 200
    body = posted.json()

    # A blocking decision with no source and a blocking credential gap both hold the build.
    assert body["satisfied"] is False
    assert set(body["blocking_open"]) == {"decision:db", "credential:sendgrid"}

    by_key = {item["key"]: item for item in body["items"]}
    assert by_key["decision:db"]["category"] == "decisions"
    assert by_key["decision:db"]["resolution"] == "needs_user"
    assert by_key["credential:sendgrid"]["category"] == "credentials"
    assert by_key["credential:sendgrid"]["resolution"] == "needs_credential"
    assert by_key["credential:sendgrid"]["provider"] == "sendgrid"
    assert by_key["credential:sendgrid"]["integration_id"] is not None

    # The read endpoint returns the same persisted assessment.
    got = client.get(f"/flow/items/{item.id}/readiness", headers=BEARER)
    assert got.status_code == 200
    assert got.json()["run_id"] == body["run_id"]


def test_readiness_satisfied_after_blocking_items_resolved(client, db_session, monkeypatch):
    _bearer(monkeypatch)
    item, _ = _project(db_session)
    client.post(f"/flow/items/{item.id}/readiness", headers=BEARER)

    # Approve every gated readiness step, the way the approval queue would.
    for step in db_session.query(AgentStep).filter(AgentStep.status == WAITING_APPROVAL).all():
        resolve_approval(db_session, step, resolution="approved", resolved_by="owner@example.com")

    got = client.get(f"/flow/items/{item.id}/readiness", headers=BEARER)
    assert got.status_code == 200
    assert got.json()["satisfied"] is True
    assert got.json()["blocking_open"] == []
