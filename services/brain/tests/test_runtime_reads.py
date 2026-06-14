"""Runtime read and aggregation endpoints, and the proof that no field is writable over HTTP.

The reads are pure projections of the ledger authored by the four writers. The runtime router
exposes no mutating method, so no protected field (status, evidence, tool_call, approval, and
the rest) can be set through any public endpoint.
"""

from app.main import app
from app.models.inbox import InboxItem
from app.models.project import Project
from app.models.user import User
from app.runtime import (
    create_run,
    propose_step,
    record_execution,
    resolve_approval,
)

BEARER = {"Authorization": "Bearer t"}


def _setup(db_session, monkeypatch):
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    user = User(email="r@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    item = InboxItem(user_id=user.id, name="Run host", body="b", status="routed", stage_history=[])
    db_session.add(item)
    db_session.flush()
    project = Project(item_id=item.id, name="Run host", slug="run-host", stage="build", mode="app")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return user, project


def _seed_run(db_session, project):
    # A run at full autonomy so steps start planned, with a mix of verified, unverified, and
    # failed outcomes plus one gated step left waiting for approval.
    run = create_run(db_session, project_id=project.id, autonomy_level=3, goal_summary="seed")
    verified = propose_step(db_session, run, title="ran a tool")
    record_execution(
        db_session, verified, outcome="completed", evidence=[{"source": "tool", "exit_code": 0}]
    )
    unverified = propose_step(db_session, run, title="reasoned only")
    record_execution(db_session, unverified, outcome="completed", evidence=[{"source": "llm"}])
    failed = propose_step(db_session, run, title="broke")
    record_execution(db_session, failed, outcome="failed", failure={"error": "boom"})
    return run, verified, unverified, failed


def test_get_run_with_steps(client, db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run, *_ = _seed_run(db_session, project)
    res = client.get(f"/runtime/runs/{run.id}", headers=BEARER)
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == run.id
    assert body["status"] == "failed"  # one step failed, all terminal
    statuses = [s["status"] for s in body["steps"]]
    assert statuses == ["completed_verified", "completed_unverified", "failed"]


def test_steps_after_cursor(client, db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run, verified, unverified, failed = _seed_run(db_session, project)
    res = client.get(
        f"/runtime/runs/{run.id}/steps", params={"after": verified.id}, headers=BEARER
    )
    assert res.status_code == 200
    ids = [s["id"] for s in res.json()]
    assert ids == [unverified.id, failed.id]


def test_approval_candidates_and_failed_steps(client, db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run, _, _, failed = _seed_run(db_session, project)
    gated = create_run(db_session, project_id=project.id, autonomy_level=0)
    waiting = propose_step(db_session, gated, title="needs approval")

    approvals = client.get(f"/runtime/runs/{gated.id}/approvals", headers=BEARER).json()
    assert [s["id"] for s in approvals] == [waiting.id]

    failures = client.get(f"/runtime/runs/{run.id}/failed", headers=BEARER).json()
    assert [s["id"] for s in failures] == [failed.id]


def test_proof_of_work_per_step(client, db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    _, verified, unverified, _ = _seed_run(db_session, project)

    proof = client.get(f"/runtime/steps/{verified.id}/proof", headers=BEARER).json()
    assert proof["verified"] is True
    assert proof["tool_evidence_count"] == 1

    proof2 = client.get(f"/runtime/steps/{unverified.id}/proof", headers=BEARER).json()
    assert proof2["verified"] is False
    assert proof2["tool_evidence_count"] == 0


def test_runs_per_project_active_and_status_counts(client, db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    done_run, *_ = _seed_run(db_session, project)
    active_run = create_run(db_session, project_id=project.id, autonomy_level=0)
    propose_step(db_session, active_run, title="waiting")  # gated -> run is waiting_approval

    per_project = client.get(
        "/runtime/runs", params={"project_id": project.id}, headers=BEARER
    ).json()
    assert {r["id"] for r in per_project} == {done_run.id, active_run.id}

    active = client.get("/runtime/runs", params={"active": True}, headers=BEARER).json()
    active_ids = {r["id"] for r in active}
    assert active_run.id in active_ids
    assert done_run.id not in active_ids  # the seeded run is terminal (failed)

    counts = client.get(f"/runtime/runs/{done_run.id}/status-counts", headers=BEARER).json()
    assert counts == {"completed_verified": 1, "completed_unverified": 1, "failed": 1}


def test_resolve_approval_then_read_reflects_it(client, db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    gated = create_run(db_session, project_id=project.id, autonomy_level=0)
    step = propose_step(db_session, gated, title="approve me")
    resolve_approval(db_session, step, resolution="approved")
    approvals = client.get(f"/runtime/runs/{gated.id}/approvals", headers=BEARER).json()
    assert approvals == []  # resolved out of the waiting queue


def test_no_protected_field_is_writable_through_any_public_endpoint():
    # The runtime ledger is authored only through the four in-process writers. Prove the HTTP
    # surface is read only: no runtime route accepts a mutating method, so status, evidence,
    # tool_call, failure, approval, and corrections can never be set over the wire.
    mutating = {"POST", "PUT", "PATCH", "DELETE"}
    offenders = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if path.startswith("/runtime") and (methods & mutating):
            offenders.append((path, sorted(methods & mutating)))
    assert offenders == []
