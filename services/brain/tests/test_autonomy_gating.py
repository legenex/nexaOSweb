"""Autonomy gating on the build engine: green-go, forced-gate, red-stop, and the kill switch.

These tests drive real build runs (a stub claude CLI on PATH, so no network and no real install) to
prove the dial disposes of what the agent proposes:

  - a green task whose change is benign auto advances start to finish: the run merges unattended,
  - a green task whose change edits an auth file is forced to the Human Gate by the classifier,
  - a git force push is refused outright at the command layer (the red, irreversible action),
  - the kill switch halts an in flight run and refuses new ones until released.
"""

import os
import stat
from pathlib import Path

import pytest

from app.agents.build_engine import (
    KillSwitchEngagedError,
    build_run_detail,
    engage_kill_switch,
    release_kill_switch,
    start_build_run,
)
from app.agents.executor import PHASE_MERGED
from app.engine import CommandRefused, prepare_workspace, run_in_workspace
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Task
from app.runtime import RUN_WAITING_APPROVAL
from app.settings import get_settings

_API_KEY = "sk-ant-autonomy-should-never-leak"


def _write_stub_claude(bin_dir, *, creates):
    """A fake claude CLI that, on a headless run, creates the given file path in the cwd.

    creates is a workspace relative path; the stub makes any parent directory and writes one line, so
    a test can steer which files a run touches and therefore what the risk classifier sees.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "if '--version' in args:\n"
        "    print('1.2.3 (Claude Code stub)')\n"
        "    sys.exit(0)\n"
        f"target = {creates!r}\n"
        "parent = os.path.dirname(target)\n"
        "if parent:\n"
        "    os.makedirs(parent, exist_ok=True)\n"
        "with open(target, 'w') as fh:\n"
        "    fh.write('one line\\n')\n"
        "print(json.dumps({\n"
        "    'type': 'result', 'subtype': 'success', 'is_error': False,\n"
        "    'result': 'done', 'total_cost_usd': 0.001,\n"
        "    'usage': {'input_tokens': 3, 'output_tokens': 2}}))\n"
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
    monkeypatch.setattr(settings, "anthropic_api_key", _API_KEY)
    return tmp_path


def _install_stub(tmp_path, monkeypatch, *, creates):
    _write_stub_claude(tmp_path / "bin", creates=creates)
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}")


def _user(db):
    user = User(email="dial@example.com", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _project(db, slug="dial-app", **kwargs):
    project = Project(name="Dial App", slug=slug, stage="build", mode="app", **kwargs)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _task(db, user, project, *, status="doing", autonomy="yellow"):
    task = Task(
        user_id=user.id,
        project_id=project.id,
        title="Build the thing",
        status=status,
        source="manual",
        autonomy=autonomy,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


# --- green auto advances ------------------------------------------------------------------


def test_green_task_with_benign_change_auto_advances(db_session, roots, tmp_path, monkeypatch):
    _install_stub(tmp_path, monkeypatch, creates="README.md")
    user = _user(db_session)
    project = _project(db_session)
    task = _task(db_session, user, project, autonomy="green")

    run = start_build_run(db_session, task=task)

    # The run merged unattended: no human resolved the gate.
    assert run.phase == PHASE_MERGED
    served = Path(roots) / "projects" / project.slug / "README.md"
    assert served.read_text(encoding="utf-8") == "one line\n"

    db_session.refresh(task)
    assert task.status == "review"

    detail = build_run_detail(db_session, run)
    assert detail["gate_step_id"] is None  # the gate was auto resolved
    assert detail["autonomy"]["effective_level"] == "green"
    assert detail["autonomy"]["auto_advance"] is True


# --- a green task that edits an auth file is forced to the gate ----------------------------


def test_green_task_editing_an_auth_file_is_forced_to_the_gate(
    db_session, roots, tmp_path, monkeypatch
):
    # The task is set green, but the change touches an auth file, so the classifier escalates it.
    _install_stub(tmp_path, monkeypatch, creates="app/security/auth.py")
    user = _user(db_session)
    project = _project(db_session, slug="auth-app")
    task = _task(db_session, user, project, autonomy="green")

    run = start_build_run(db_session, task=task)

    # It did NOT auto advance: it is parked at the Human Gate, nothing merged.
    assert run.status == RUN_WAITING_APPROVAL
    assert run.phase != PHASE_MERGED
    assert not (Path(roots) / "projects" / project.slug / "app" / "security" / "auth.py").exists()

    db_session.refresh(task)
    assert task.status == "agent_working"

    detail = build_run_detail(db_session, run)
    assert detail["gate_step_id"] is not None
    assert detail["autonomy"]["effective_level"] == "yellow"
    assert detail["autonomy"]["auto_advance"] is False
    assert "auth" in detail["autonomy"]["categories"]


# --- a force push is refused as red -------------------------------------------------------


def test_force_push_is_refused_at_the_command_layer(db_session, roots):
    # The red, irreversible action never reaches the shell: the guarded runner refuses it.
    project = _project(db_session, slug="force-app")
    ws = prepare_workspace(project)
    with pytest.raises(CommandRefused):
        run_in_workspace(ws, "git push --force origin work")
    with pytest.raises(CommandRefused):
        run_in_workspace(ws, "git push origin main")


# --- the kill switch halts an in flight run -----------------------------------------------


def test_kill_switch_halts_an_in_flight_run_and_refuses_new_ones(
    db_session, roots, tmp_path, monkeypatch
):
    _install_stub(tmp_path, monkeypatch, creates="README.md")
    user = _user(db_session)
    project = _project(db_session, slug="kill-app")
    # A yellow task parks at the gate, so the run is in flight (active, awaiting review).
    task = _task(db_session, user, project, autonomy="yellow", status="doing")

    run = start_build_run(db_session, task=task)
    assert run.status == RUN_WAITING_APPROVAL

    # Engage the kill switch: the in flight run is halted and the task restored.
    halted = engage_kill_switch(db_session, project, resolved_by="dial@example.com")
    assert [r.id for r in halted] == [run.id]
    db_session.refresh(run)
    db_session.refresh(task)
    db_session.refresh(project)
    assert run.phase == "cancelled"
    assert run.status not in ("waiting_approval", "executing", "planned")
    assert task.status == "doing"
    assert project.agent_kill_switch is True

    # A new run is refused while the switch stays engaged.
    task2 = _task(db_session, user, project, autonomy="green", status="todo")
    with pytest.raises(KillSwitchEngagedError):
        start_build_run(db_session, task=task2)

    # Releasing the switch lets runs start again.
    release_kill_switch(db_session, project)
    db_session.refresh(project)
    assert project.agent_kill_switch is False
    run2 = start_build_run(db_session, task=task2)
    assert run2.phase == PHASE_MERGED  # task2 is green and benign, so it auto advances
