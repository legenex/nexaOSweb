"""The deferred outcome seam: an outcome row written on approve, on reject, and on a later revert.

These drive the real stub backed build path and assert OutcomeLog captures the human verdict and,
for an approved change later rejected, the revert. This is recording only; nothing reads these rows
to rank or learn yet (see docs/ARCHITECTURE.md).
"""

import stat

import pytest

from app.agents.build_engine import (
    approve_build_run,
    reject_build_run,
    start_build_run,
)
from app.models.outcome import OutcomeLog
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Task
from app.outcomes import OutcomeError, record_outcome
from app.runtime import create_run
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
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-ant-outcome-no-leak")


def _user(db):
    user = User(email="verdict@example.com", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _project(db, slug="outcome-app"):
    project = Project(name="Outcome App", slug=slug, stage="build", mode="app")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _task(db, user, project):
    task = Task(
        user_id=user.id,
        project_id=project.id,
        title="Create README.md with one line",
        status="doing",
        source="manual",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _outcome(db, run_id):
    return db.query(OutcomeLog).filter(OutcomeLog.run_id == run_id).one()


def test_approve_writes_an_approved_outcome(db_session, roots, stub_backend):
    user = _user(db_session)
    project = _project(db_session)
    run = start_build_run(db_session, task=_task(db_session, user, project))
    approve_build_run(db_session, run, resolved_by=user.email)

    row = _outcome(db_session, run.id)
    assert row.verdict == "approved" and row.reverted is False
    assert row.project_id == project.id


def test_reject_writes_a_rejected_outcome(db_session, roots, stub_backend):
    user = _user(db_session)
    project = _project(db_session)
    run = start_build_run(db_session, task=_task(db_session, user, project))
    reject_build_run(db_session, run, resolved_by=user.email)

    row = _outcome(db_session, run.id)
    assert row.verdict == "rejected" and row.reverted is False


def test_revert_of_an_approved_change_sets_reverted(db_session, roots, stub_backend):
    user = _user(db_session)
    project = _project(db_session)
    run = start_build_run(db_session, task=_task(db_session, user, project))
    approve_build_run(db_session, run, resolved_by=user.email)
    assert _outcome(db_session, run.id).reverted is False

    # Rejecting a run whose change has already merged reverts it through the rollback path.
    reject_build_run(db_session, run, resolved_by=user.email)
    row = _outcome(db_session, run.id)
    assert row.verdict == "approved" and row.reverted is True
    # Still one row for the run: the revert updated the existing outcome, never added a second.
    assert db_session.query(OutcomeLog).filter(OutcomeLog.run_id == run.id).count() == 1


def test_record_outcome_rejects_an_unknown_verdict(db_session):
    project = _project(db_session)
    run = create_run(db_session, project_id=project.id)
    with pytest.raises(OutcomeError):
        record_outcome(db_session, run, verdict="maybe")
