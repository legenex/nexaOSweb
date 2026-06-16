"""Per run usage and the project cost rollup.

A build run records its cost and token usage as the backend reports it: the cost is denormalised on
the run, the token counts live on the build step's tool evidence. These tests drive the real stub
backed build path and prove the usage is recorded non-null and surfaced, that the project cost
rollup sums it by backend, that a backend over its cost ceiling is skipped with a reason and an
audit row, and that a budget breach pauses dispatch with an audit row.
"""

import stat

import pytest

from app.agents.build_engine import BackendUnavailableError, run_usage, start_build_run
from app.agents.cost import project_cost_rollup
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Task
from app.settings import get_settings

_API_KEY = "sk-ant-cost-should-never-leak"


def _write_stub_claude(bin_dir, *, cost=0.0012, input_tokens=11, output_tokens=7):
    """A fake claude CLI: answers --version and, on a headless run, creates README.md and reports
    a cost and token usage so the cost surface has real figures to record."""
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
        f"    'total_cost_usd': {cost},\n"
        f"    'usage': {{'input_tokens': {input_tokens}, 'output_tokens': {output_tokens}}},\n"
        "}))\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script


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
    monkeypatch.setattr(get_settings(), "anthropic_api_key", _API_KEY)


def _user(db):
    user = User(email="cost@example.com", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _project(db, slug="cost-app"):
    project = Project(name="Cost App", slug=slug, stage="build", mode="app")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _task(db, user, project, *, status="doing"):
    task = Task(
        user_id=user.id,
        project_id=project.id,
        title="Create README.md with one line",
        status=status,
        source="manual",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


# --- Part A: usage recorded and surfaced --------------------------------------------------


def test_run_records_non_null_usage(db_session, roots, stub_backend):
    user = _user(db_session)
    project = _project(db_session)
    task = _task(db_session, user, project)

    run = start_build_run(db_session, task=task, proposed_by="cost@example.com")

    usage = run_usage(db_session, run)
    assert usage["cost_usd"] == pytest.approx(0.0012)
    assert usage["input_tokens"] == 11
    assert usage["output_tokens"] == 7


# --- Part C: the cost rollup --------------------------------------------------------------


def test_cost_rollup_sums_real_usage_by_backend(db_session, roots, stub_backend):
    user = _user(db_session)
    project = _project(db_session)
    start_build_run(db_session, task=_task(db_session, user, project), proposed_by=user.email)
    start_build_run(db_session, task=_task(db_session, user, project), proposed_by=user.email)

    rollup = project_cost_rollup(db_session, project.id)
    assert rollup["run_count"] == 2
    assert rollup["total_usd"] == pytest.approx(0.0024)
    assert rollup["input_tokens"] == 22
    assert rollup["output_tokens"] == 14
    assert len(rollup["by_backend"]) == 1
    claude = rollup["by_backend"][0]
    assert claude["backend"] == "claude-code"
    assert claude["run_count"] == 2
    assert claude["cost_usd"] == pytest.approx(0.0024)


def test_cost_rollup_endpoint(client, db_session, roots, stub_backend, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    bearer = {"Authorization": "Bearer t"}
    user = _user(db_session)  # bearer acts as the earliest user
    project = _project(db_session)
    start_build_run(db_session, task=_task(db_session, user, project), proposed_by=user.email)

    res = client.get(f"/agents/projects/{project.id}/cost", headers=bearer)
    assert res.status_code == 200
    body = res.json()
    assert body["run_count"] == 1 and body["total_usd"] == pytest.approx(0.0012)


# --- Part C: the per backend cost ceiling -------------------------------------------------


def test_over_ceiling_backend_is_skipped_with_a_reason_and_an_audit_row(
    db_session, roots, stub_backend
):
    from app.models.audit import AgentAudit
    from app.models.runtime import AgentRun

    user = _user(db_session)
    project = _project(db_session)
    # Seed history that puts claude-code's projected cost above its $5 ceiling. The stub makes
    # claude-code available, so the only reason to skip it is the ceiling, not availability. No
    # other backend has a stub on PATH, so the order is exhausted and the run cannot start.
    db_session.add(
        AgentRun(project_id=project.id, backend="claude-code", cost_usd=10.0, kind="executor")
    )
    db_session.commit()

    with pytest.raises(BackendUnavailableError):
        start_build_run(db_session, task=_task(db_session, user, project), proposed_by=user.email)

    select = (
        db_session.query(AgentAudit)
        .filter(AgentAudit.category == "backend", AgentAudit.action == "select")
        .order_by(AgentAudit.id.desc())
        .first()
    )
    assert select is not None
    considered = select.detail["trail"]["considered"]
    claude = next(c for c in considered if c["backend"] == "claude-code")
    assert claude["over_ceiling"] is True
    assert "ceiling" in claude["reason"]


# --- Part C: the project budget pauses dispatch -------------------------------------------


def test_budget_breach_pauses_dispatch_with_an_audit_row(db_session, roots, monkeypatch):
    from app.agents.cost import set_project_budget
    from app.agents.orchestrator import orchestrate_project
    from app.models.audit import AgentAudit
    from app.models.runtime import AgentRun

    monkeypatch.setattr(get_settings(), "nexa_enable_orchestrator", True)
    project = _project(db_session)
    project.stage = "approved"
    db_session.commit()

    # A tiny daily budget, already breached by a recorded run today.
    set_project_budget(db_session, project.id, daily_usd=0.001)
    db_session.add(
        AgentRun(project_id=project.id, backend="claude-code", cost_usd=1.0, kind="executor")
    )
    db_session.commit()

    state = orchestrate_project(db_session, project)
    assert state["status"] == "paused"
    assert state["runs_dispatched"] == 0

    pause = (
        db_session.query(AgentAudit)
        .filter(AgentAudit.category == "orchestrator", AgentAudit.action == "pause")
        .one()
    )
    assert pause.reason == "budget_daily"
    assert pause.actor_type == "system"
