"""End-to-end runtime dogfood on real data.

Two roundtrips drive the runtime the way the executor eventually will. The first proposes and
records a mix of outcomes and reads them back through the public API. The second logs a real
file delete, against a real file on disk through the real projects endpoint, as a verified step
backed by tool evidence, proving the ledger records truth and not a simulation.
"""

from app.models.inbox import InboxItem
from app.models.project import BuildLogEntry, Project
from app.models.user import User
from app.runtime import (
    COMPLETED_UNVERIFIED,
    COMPLETED_VERIFIED,
    FAILED,
    create_run,
    propose_step,
    record_execution,
)
from app.settings import get_settings

BEARER = {"Authorization": "Bearer t"}


def _setup(db_session, tmp_path, monkeypatch, *, slug="dogfood-app"):
    monkeypatch.setattr(get_settings(), "nexa_projects_root", str(tmp_path / "projects"))
    monkeypatch.setattr(get_settings(), "nexa_runtime_root", str(tmp_path / "runtime"))
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    user = User(email="d@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    item = InboxItem(user_id=user.id, name="Dogfood", body="b", status="routed", stage_history=[])
    db_session.add(item)
    db_session.flush()
    project = Project(item_id=item.id, name="Dogfood", slug=slug, stage="build", mode="app")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return user, project


def test_roundtrip_reads_back_mixed_verified_unverified_and_failed(
    client, db_session, tmp_path, monkeypatch
):
    _, project = _setup(db_session, tmp_path, monkeypatch)
    run = create_run(
        db_session, project_id=project.id, autonomy_level=3, goal_summary="trivial run"
    )

    verified = propose_step(db_session, run, kind="check", title="run the test suite")
    record_execution(
        db_session,
        verified,
        outcome="completed",
        evidence=[{"source": "tool", "command": "pytest", "exit_code": 0}],
        tool_call={"name": "shell", "args": ["pytest", "-q"]},
    )
    unverified = propose_step(db_session, run, kind="note", title="summarise the change")
    record_execution(
        db_session, unverified, outcome="completed", evidence=[{"source": "llm", "note": "ok"}]
    )
    failed = propose_step(db_session, run, kind="deploy", title="attempt deploy")
    record_execution(db_session, failed, outcome="failed", failure={"error": "no credentials"})

    body = client.get(f"/runtime/runs/{run.id}", headers=BEARER).json()
    by_title = {s["title"]: s for s in body["steps"]}
    assert by_title["run the test suite"]["status"] == COMPLETED_VERIFIED
    assert by_title["summarise the change"]["status"] == COMPLETED_UNVERIFIED
    assert by_title["attempt deploy"]["status"] == FAILED
    assert body["status"] == "failed"  # one terminal failure colours the run

    counts = client.get(f"/runtime/runs/{run.id}/status-counts", headers=BEARER).json()
    assert counts == {"completed_verified": 1, "completed_unverified": 1, "failed": 1}


def test_logs_a_real_file_delete_as_a_verified_step(client, db_session, tmp_path, monkeypatch):
    _, project = _setup(db_session, tmp_path, monkeypatch)
    # Real data: a real file in the project folder on disk.
    folder = tmp_path / "projects" / project.slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "scratch.md").write_text("# scratch\n\ndelete me\n", encoding="utf-8")

    run = create_run(db_session, project_id=project.id, autonomy_level=3, goal_summary="cleanup")
    step = propose_step(
        db_session, run, kind="file_delete", title="delete scratch.md", intent="remove scratch"
    )

    # Perform the real deletion through the real projects endpoint, then record its real result.
    res = client.delete(
        f"/projects/{project.id}/files", params={"path": "scratch.md"}, headers=BEARER
    )
    assert res.status_code == 200
    assert res.json() == {"path": "scratch.md", "deleted": True}
    assert not (folder / "scratch.md").exists()  # the file is genuinely gone

    recorded = record_execution(
        db_session,
        step,
        outcome="completed",
        evidence=[
            {"source": "tool", "action": "file_delete", "path": "scratch.md", "result": res.json()}
        ],
        tool_call={"endpoint": "DELETE /projects/{project_id}/files", "path": "scratch.md"},
    )
    # The delete is recorded as verified truth, earned from the tool result.
    assert recorded.status == COMPLETED_VERIFIED

    proof = client.get(f"/runtime/steps/{step.id}/proof", headers=BEARER).json()
    assert proof["verified"] is True
    assert proof["tool_evidence_count"] == 1
    assert proof["evidence"][0]["path"] == "scratch.md"

    # The deletion also left its own real audit trail in the project build log.
    log = (
        db_session.query(BuildLogEntry)
        .filter(BuildLogEntry.project_id == project.id, BuildLogEntry.action == "delete")
        .all()
    )
    assert any(entry.file_path == "scratch.md" for entry in log)
