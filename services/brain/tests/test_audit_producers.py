"""Audit producers: every governed event writes its audit row from its real call site.

This drives the build engine and the orchestrator through their real paths (a stub backed run, an
approve, a reject, a kill switch engage and release that cancels an in flight run, and an
orchestrator pause and resume) and asserts one audit row per event type appears, written by the
call sites themselves. Nothing here calls a record_audit helper directly: if a row is present the
producer is wired.
"""

import stat

import pytest

from app.agents.build_engine import (
    approve_build_run,
    engage_kill_switch,
    reject_build_run,
    release_kill_switch,
    start_build_run,
)
from app.agents.orchestrator import pause_loop, resume_loop
from app.models.audit import AgentAudit
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Task
from app.settings import get_settings


def _write_stub_claude(bin_dir):
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "if '--version' in args:\n"
        "    print('1.2.3 (Claude Code stub)')\n"
        "    sys.exit(0)\n"
        "with open('README.md', 'w') as fh:\n"
        "    fh.write('one line\\n')\n"
        "print(json.dumps({\n"
        "    'type': 'result', 'subtype': 'success', 'is_error': False,\n"
        "    'result': 'Created README.md with one line.',\n"
        "    'total_cost_usd': 0.0012,\n"
        "    'usage': {'input_tokens': 11, 'output_tokens': 7},\n"
        "}))\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture()
def roots(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "nexa_projects_root", str(tmp_path / "projects"))
    monkeypatch.setattr(settings, "nexa_runtime_root", str(tmp_path / "runtime"))
    return tmp_path


@pytest.fixture()
def stub_backend(tmp_path, monkeypatch):
    import os

    _write_stub_claude(tmp_path / "bin")
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-ant-producers-no-leak")


def _user(db):
    user = User(email="ops@example.com", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _project(db, slug="producers-app"):
    project = Project(name="Producers App", slug=slug, stage="build", mode="app")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _task(db, user, project, title="Create README.md with one line"):
    task = Task(
        user_id=user.id, project_id=project.id, title=title, status="doing", source="manual"
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _start(db, user, project):
    return start_build_run(db, task=_task(db, user, project), proposed_by=user.email)


def _pairs(db):
    return {(row.category, row.action) for row in db.query(AgentAudit).all()}


def test_every_event_type_is_written_from_its_call_site(db_session, roots, stub_backend):
    user = _user(db_session)
    project = _project(db_session)

    # 1) Start + approve: run_start, backend select, gate decision, approval/approve.
    run1 = _start(db_session, user, project)
    approve_build_run(db_session, run1, resolved_by=user.email)

    # 2) Start + reject: approval/reject.
    run2 = _start(db_session, user, project)
    reject_build_run(db_session, run2, resolved_by=user.email)

    # 3) Start, then engage the kill switch: it cancels the in flight run (approval/cancel) and
    #    records kill_switch/engage; release records kill_switch/release.
    _start(db_session, user, project)
    engage_kill_switch(db_session, project, resolved_by=user.email)
    release_kill_switch(db_session, project, resolved_by=user.email)

    # 4) Orchestrator pause and resume through the real loop functions.
    pause_loop(db_session, project, actor=user.email)
    resume_loop(db_session, project, actor=user.email)

    pairs = _pairs(db_session)
    expected = {
        ("run", "run_start"),
        ("backend", "select"),
        ("gate", "decision"),
        ("approval", "approve"),
        ("approval", "reject"),
        ("approval", "cancel"),
        ("kill_switch", "engage"),
        ("kill_switch", "release"),
        ("orchestrator", "pause"),
        ("orchestrator", "resume"),
    }
    missing = expected - pairs
    assert not missing, f"no audit row from the call site for: {sorted(missing)}"


def test_audit_rows_carry_the_right_actor(db_session, roots, stub_backend):
    user = _user(db_session)
    project = _project(db_session)
    run = _start(db_session, user, project)
    approve_build_run(db_session, run, resolved_by=user.email)

    run_start = (
        db_session.query(AgentAudit)
        .filter(AgentAudit.category == "run", AgentAudit.action == "run_start")
        .one()
    )
    assert run_start.actor == user.email and run_start.actor_type == "user"
    # The backend selection is the system's policy decision, recorded as a system actor.
    backend = (
        db_session.query(AgentAudit)
        .filter(AgentAudit.category == "backend", AgentAudit.action == "select")
        .first()
    )
    assert backend is not None and backend.actor_type == "system"
