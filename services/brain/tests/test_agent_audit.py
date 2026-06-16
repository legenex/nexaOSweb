"""Agent governance audit log: the writer, the append-only guarantee, redaction, and the reads.

The build engine and orchestrator write one audit row per governed moment through app/audit.py.
These tests prove each event type writes exactly one row carrying the right actor and reason, that a
secret can never reach a row, that the log is append-only (no update, no delete), and that the read
endpoints filter by project, run, category, and actor while scoping to the owning user. A final test
drives the whole Alembic chain up, down, and up again to prove a single head that round-trips.
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
    project = Project(name="Host", slug="host", stage="build", mode="app")
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
    assert row.project_id == project.id and row.run_id == run.id


def test_run_start_by_system_is_labelled_system(db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run = create_run(db_session, project_id=project.id)
    row = audit_run_start(db_session, run, actor="system:autonomy-green")
    assert row.actor_type == "system"


def test_backend_selection_writes_one_row_with_trail(db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run = create_run(db_session, project_id=project.id)
    trail = {
        "chosen": "claude-code",
        "policy_source": "default",
        "order": ["claude-code", "codex-cli"],
        "considered": [{"backend": "claude-code", "over_ceiling": False, "chosen": True}],
        "reason": "selected claude-code (default)",
    }
    row = audit_backend_selection(db_session, run=run, trail=trail, reason="picked claude-code")
    assert db_session.query(AgentAudit).count() == 1
    assert (row.category, row.action) == ("backend", "select")
    assert row.actor_type == "system" and row.actor == "system"
    assert row.detail["trail"] == trail


def test_gate_decision_writes_one_row_with_level_categories_reasons(db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run = create_run(db_session, project_id=project.id)
    row = audit_gate_decision(
        db_session,
        run=run,
        effective_level="red",
        categories=["force_push", "auth"],
        reasons=["force_push: matched 'git push --force'", "auth: matched 'login'"],
        step_id=42,
    )
    assert db_session.query(AgentAudit).count() == 1
    assert (row.category, row.action) == ("gate", "decision")
    assert row.detail["effective_level"] == "red"
    assert row.detail["categories"] == ["force_push", "auth"]
    # With no explicit reason the helper summarises the reasons so the column is never empty.
    assert row.reason.startswith("force_push:")
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
        db_session,
        action=action,
        actor="owner@example.com",
        reason=f"{action} all runs",
        project_id=project.id,
    )
    assert db_session.query(AgentAudit).count() == 1
    assert (row.category, row.action) == ("kill_switch", action)
    assert row.actor_type == "user" and row.reason == f"{action} all runs"


@pytest.mark.parametrize("action", ["pause", "resume"])
def test_orchestrator_events_each_write_one_row(db_session, monkeypatch, action):
    _, project = _setup(db_session, monkeypatch)
    row = audit_orchestrator(
        db_session, action=action, actor="system", reason=action, project_id=project.id
    )
    assert db_session.query(AgentAudit).count() == 1
    assert (row.category, row.action) == ("orchestrator", action)
    assert row.actor_type == "system"


def test_unknown_category_or_action_is_refused(db_session):
    with pytest.raises(AuditError):
        record_audit(db_session, category="bogus", action="x", actor="system")
    with pytest.raises(AuditError):
        record_audit(db_session, category="run", action="not_a_run_action", actor="system")
    with pytest.raises(AuditError):
        record_audit(db_session, category="run", action="run_start", actor="x", actor_type="robot")
    assert db_session.query(AgentAudit).count() == 0


# --- secrets never land in a row ----------------------------------------------------------


def test_secret_in_detail_is_refused_and_no_row_written(db_session):
    with pytest.raises(SecretLeakError):
        record_audit(
            db_session,
            category="backend",
            action="select",
            actor="system",
            detail={"trail": {"considered": [{"backend": "claude-code", "api_key": "sk-secret"}]}},
        )
    assert db_session.query(AgentAudit).count() == 0


def test_reference_to_a_stored_secret_is_allowed(db_session):
    row = record_audit(
        db_session,
        category="backend",
        action="select",
        actor="system",
        detail={"trail": {"credentials_ref": "secret://anthropic"}},
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
    assert audit_retention(db_session) == {"mode": "keep_all", "max_days": None}


# --- read endpoints and filters ------------------------------------------------------------


def test_audit_feed_filters_by_run_category_actor(client, db_session, monkeypatch):
    _, project = _setup(db_session, monkeypatch)
    run_a = create_run(db_session, project_id=project.id)
    run_b = create_run(db_session, project_id=project.id)
    audit_run_start(db_session, run_a, actor="owner@example.com", reason="a")
    audit_backend_selection(db_session, run=run_a, trail={}, reason="trail")
    audit_run_start(db_session, run_b, actor="owner@example.com", reason="b")
    audit_kill_switch(db_session, action="engage", actor="owner@example.com", reason="halt")

    everything = client.get("/agents/audit", headers=BEARER).json()
    assert len(everything) == 4
    assert everything[0]["category"] == "kill_switch"  # newest first

    by_run = client.get("/agents/audit", params={"run_id": run_a.id}, headers=BEARER).json()
    assert {r["category"] for r in by_run} == {"run", "backend"}

    by_cat = client.get("/agents/audit", params={"category": "run"}, headers=BEARER).json()
    assert len(by_cat) == 2 and all(r["category"] == "run" for r in by_cat)

    by_actor = client.get(
        "/agents/audit", params={"actor": "owner@example.com"}, headers=BEARER
    ).json()
    assert len(by_actor) == 3  # the three user events, not the system backend select


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


# --- the whole migration chain: single head, up and down round-trip ------------------------


def test_migration_chain_single_head_and_round_trips(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine

    from app.settings import get_settings

    cfg = Config("alembic.ini")
    # Exactly one head: a second head would mean a migration chained off a stale revision.
    assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1

    db_file = tmp_path / "roundtrip.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    get_settings.cache_clear()
    try:
        command.upgrade(cfg, "head")
        engine = create_engine(f"sqlite:///{db_file}")
        assert "agent_audit" in inspect(engine).get_table_names()

        # Down through the whole chain, then back up: proves every revision round-trips.
        command.downgrade(cfg, "base")
        assert "agent_audit" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "head")
        assert "agent_audit" in inspect(engine).get_table_names()
        engine.dispose()
    finally:
        get_settings.cache_clear()
