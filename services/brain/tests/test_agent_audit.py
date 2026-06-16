"""Agent governance audit log: the writer, the append-only guarantee, redaction, and the reads.

The build engine writes one audit row per governed moment through app/audit.py. These tests prove
each event type writes exactly one row carrying the right actor and reason, that a secret can never
reach a row, that the log is append-only (no update, no delete), and that the read endpoints filter
by project, run, category, and actor while scoping to the owning user. A final test drives the
Alembic migration up and back down to prove it round-trips.
"""

import pytest
from sqlalchemy import inspect

from app.audit import (
    AuditError,
    audit_approval,
    audit_backend_selection,
    audit_gate_decision,
    audit_kill_switch,
    audit_orchestrator,
    audit_retention,
    audit_run_start,
    record_audit,
)
from app.models.audit import AgentAudit, AuditAppendOnlyError
from app.models.inbox import InboxItem
from app.models.project import Project
from app.models.user import User
from app.runtime import create_run
from app.security.redaction import SecretLeakError

BEARER = {"Authorization": "Bearer t"}


def _setup(db_session, monkeypatch):
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    user = User(email="owner@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    item = InboxItem(user_id=user.id, name="Host", body="b", status="routed", stage_history=[])
    db_session.add(item)
    db_session.flush()
    project = Project(item_id=item.id, name="Host", slug="host", stage="build", mode="app")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return user, project


# --- one row per event type, with the right actor and reason ------------------------------


def test_run_start_writes_one_row(db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run = create_run(db_session, project_id=project.id, autonomy_level=0)
    row = audit_run_start(db_session, run, actor="owner@example.com", reason="user kicked it off")
    assert db_session.query(AgentAudit).count() == 1
    assert (row.category, row.action) == ("run", "run_start")
    assert row.actor_type == "user" and row.actor == "owner@example.com"
    assert row.reason == "user kicked it off"
    # project_id is backfilled from the run so the row is self describing.
    assert row.project_id == project.id and row.run_id == run.id


def test_backend_selection_writes_one_row_with_trail(db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run = create_run(db_session, project_id=project.id)
    trail = [
        {"backend": "local", "considered": True, "chosen": False, "why": "no gpu"},
        {"backend": "anthropic", "considered": True, "chosen": True, "why": "agentic_code key"},
    ]
    row = audit_backend_selection(db_session, run=run, trail=trail, reason="picked anthropic")
    assert db_session.query(AgentAudit).count() == 1
    assert (row.category, row.action) == ("backend", "select")
    assert row.actor_type == "system" and row.actor == "system"
    assert row.reason == "picked anthropic"
    assert row.detail["trail"] == trail


def test_gate_decision_writes_one_row_with_level_categories_reasons(db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run = create_run(db_session, project_id=project.id)
    row = audit_gate_decision(
        db_session,
        run=run,
        effective_level=0,
        categories=["destructive", "production"],
        reasons=["touches prod", "irreversible delete"],
        step_id=42,
    )
    assert db_session.query(AgentAudit).count() == 1
    assert (row.category, row.action) == ("gate", "decision")
    assert row.detail["effective_level"] == 0
    assert row.detail["categories"] == ["destructive", "production"]
    assert row.detail["reasons"] == ["touches prod", "irreversible delete"]
    # With no explicit reason the helper summarises the reasons so the column is never empty.
    assert row.reason == "touches prod; irreversible delete"
    assert row.step_id == 42


@pytest.mark.parametrize("action", ["approve", "reject", "cancel"])
def test_approval_events_each_write_one_row(db_session, monkeypatch, action):
    _, project = _setup(db_session, monkeypatch)
    run = create_run(db_session, project_id=project.id)
    row = audit_approval(
        db_session, action=action, actor="owner@example.com", reason=f"{action} note", run=run
    )
    assert db_session.query(AgentAudit).count() == 1
    assert (row.category, row.action) == ("approval", action)
    assert row.actor_type == "user" and row.actor == "owner@example.com"
    assert row.reason == f"{action} note"


@pytest.mark.parametrize("action", ["engage", "release"])
def test_kill_switch_events_each_write_one_row(db_session, monkeypatch, action):
    _, project = _setup(db_session, monkeypatch)
    row = audit_kill_switch(
        db_session, action=action, actor="owner@example.com", reason=f"{action} all runs"
    )
    assert db_session.query(AgentAudit).count() == 1
    assert (row.category, row.action) == ("kill_switch", action)
    assert row.actor_type == "user" and row.reason == f"{action} all runs"


@pytest.mark.parametrize("action", ["pause", "resume"])
def test_orchestrator_events_each_write_one_row(db_session, monkeypatch, action):
    _, project = _setup(db_session, monkeypatch)
    run = create_run(db_session, project_id=project.id)
    row = audit_orchestrator(db_session, action=action, actor="system", reason=f"{action}", run=run)
    assert db_session.query(AgentAudit).count() == 1
    assert (row.category, row.action) == ("orchestrator", action)
    assert row.actor_type == "system"


def test_unknown_category_or_action_is_refused(db_session):
    with pytest.raises(AuditError):
        record_audit(db_session, category="bogus", action="x", actor="system")
    with pytest.raises(AuditError):
        record_audit(db_session, category="run", action="not_a_run_action", actor="system")
    with pytest.raises(AuditError):
        record_audit(
            db_session, category="run", action="run_start", actor="x", actor_type="robot"
        )
    assert db_session.query(AgentAudit).count() == 0


# --- secrets never land in a row ----------------------------------------------------------


def test_secret_in_detail_is_refused_and_no_row_written(db_session):
    with pytest.raises(SecretLeakError):
        record_audit(
            db_session,
            category="backend",
            action="select",
            actor="system",
            detail={"trail": [{"backend": "anthropic", "api_key": "sk-live-supersecret"}]},
        )
    assert db_session.query(AgentAudit).count() == 0


def test_reference_to_a_stored_secret_is_allowed(db_session):
    # A pointer into the secret store is the sanctioned shape and must not trip the guard.
    row = record_audit(
        db_session,
        category="backend",
        action="select",
        actor="system",
        detail={"trail": [{"backend": "anthropic", "credentials_ref": "secret://anthropic"}]},
    )
    assert row.id is not None


# --- append-only ---------------------------------------------------------------------------


def test_audit_row_cannot_be_updated(db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run = create_run(db_session, project_id=project.id)
    row = audit_run_start(db_session, run, actor="owner@example.com")
    row.reason = "tampered"
    with pytest.raises(AuditAppendOnlyError):
        db_session.commit()
    db_session.rollback()
    assert db_session.get(AgentAudit, row.id).reason == ""


def test_audit_row_cannot_be_deleted(db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run = create_run(db_session, project_id=project.id)
    row = audit_run_start(db_session, run, actor="owner@example.com")
    db_session.delete(row)
    with pytest.raises(AuditAppendOnlyError):
        db_session.commit()
    db_session.rollback()
    assert db_session.query(AgentAudit).count() == 1


# --- retention default ---------------------------------------------------------------------


def test_retention_defaults_to_keep_all(db_session):
    policy = audit_retention(db_session)
    assert policy == {"mode": "keep_all", "max_days": None}


# --- read endpoints and filters ------------------------------------------------------------


def test_audit_feed_filters_by_project_run_category_actor(client, db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run_a = create_run(db_session, project_id=project.id)
    run_b = create_run(db_session, project_id=project.id)
    audit_run_start(db_session, run_a, actor="owner@example.com", reason="a")
    audit_backend_selection(db_session, run=run_a, trail=[], reason="trail")
    audit_run_start(db_session, run_b, actor="owner@example.com", reason="b")
    audit_kill_switch(db_session, action="engage", actor="owner@example.com", reason="halt")

    everything = client.get("/agents/audit", headers=BEARER).json()
    assert len(everything) == 4
    # Newest first.
    assert everything[0]["category"] == "kill_switch"

    by_run = client.get("/agents/audit", params={"run_id": run_a.id}, headers=BEARER).json()
    assert {r["category"] for r in by_run} == {"run", "backend"}

    by_cat = client.get("/agents/audit", params={"category": "run"}, headers=BEARER).json()
    assert len(by_cat) == 2 and all(r["category"] == "run" for r in by_cat)

    by_actor = client.get(
        "/agents/audit", params={"actor": "owner@example.com"}, headers=BEARER
    ).json()
    assert len(by_actor) == 3  # the three user events, not the system backend select

    by_project = client.get(
        "/agents/audit", params={"project_id": project.id}, headers=BEARER
    ).json()
    # The kill switch row carries no project; the three run/backend rows do.
    assert {r["category"] for r in by_project} == {"run", "backend"}


def test_unknown_category_filter_is_rejected(client, db_session, monkeypatch):
    _setup(db_session, monkeypatch)
    res = client.get("/agents/audit", params={"category": "nope"}, headers=BEARER)
    assert res.status_code == 422


def test_project_audit_endpoint_scopes_to_the_project(client, db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run = create_run(db_session, project_id=project.id)
    audit_run_start(db_session, run, actor="owner@example.com", reason="started")
    audit_kill_switch(db_session, action="engage", actor="owner@example.com")  # no project

    rows = client.get(f"/agents/projects/{project.id}/audit", headers=BEARER).json()
    assert [r["category"] for r in rows] == ["run"]


def test_project_audit_404_for_unknown_project(client, db_session, monkeypatch):
    _setup(db_session, monkeypatch)
    res = client.get("/agents/projects/9999/audit", headers=BEARER)
    assert res.status_code == 404


def test_audit_reads_scope_out_another_users_project(client, db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run = create_run(db_session, project_id=project.id)
    audit_run_start(db_session, run, actor="owner@example.com")

    # A second user owns a different project; its rows must not surface for the bearer user, and
    # neither may the first user's project rows once we ask as the stranger. Here we prove the
    # first project's rows are invisible when queried under a project the bearer cannot see.
    stranger = User(email="stranger@example.com", password_hash="x")
    db_session.add(stranger)
    db_session.flush()
    other_item = InboxItem(
        user_id=stranger.id, name="Other", body="b", status="routed", stage_history=[]
    )
    db_session.add(other_item)
    db_session.flush()
    other_project = Project(
        item_id=other_item.id, name="Other", slug="other", stage="build", mode="app"
    )
    db_session.add(other_project)
    db_session.commit()
    db_session.refresh(other_project)
    other_run = create_run(db_session, project_id=other_project.id)
    audit_run_start(db_session, other_run, actor="stranger@example.com")

    # The bearer maps to the InboxItem owner of the first project. The cross run feed must omit the
    # stranger's project rows.
    feed = client.get("/agents/audit", headers=BEARER).json()
    project_ids = {r["project_id"] for r in feed}
    assert other_project.id not in project_ids


# --- migration round-trips -----------------------------------------------------------------


def test_migration_0019_round_trips(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    from app.settings import get_settings

    db_file = tmp_path / "roundtrip.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")

        from sqlalchemy import create_engine

        engine = create_engine(f"sqlite:///{db_file}")
        assert "agent_audit" in inspect(engine).get_table_names()

        command.downgrade(cfg, "0018_models_connect")
        assert "agent_audit" not in inspect(engine).get_table_names()
        engine.dispose()
    finally:
        get_settings.cache_clear()
