"""The orchestrator loop: autonomy gated dispatch over a sliced task graph.

These tests drive the loop at the service layer with a stub claude CLI on PATH (no network, no real
install) and the orchestrator flag on. Each generated task's stub creates a file unique to its run, so
every dispatch produces a real, non empty, benign diff. The tests prove the acceptance: a green only
graph runs to completion unattended, a yellow node pauses its branch until a human approve resumes it,
a red node never auto runs, the kill switch refuses dispatch, an unapproved project is refused, and the
run cap and the time budget each stop the loop. A separate check confirms a force push is still
refused, and the HTTP refusals are checked through the endpoint.
"""

import os
import stat

import pytest

from app.agents.build_engine import approve_build_run
from app.agents.executor import PHASE_MERGED
from app.agents.orchestrator import (
    OrchestratorDisabledError,
    OrchestratorHaltedError,
    OrchestratorNotApprovedError,
    orchestrate_project,
    orchestration_state,
    pause_loop,
)
from app.engine import CommandRefused, prepare_workspace, run_in_workspace
from app.models.project import Project
from app.models.runtime import AgentRun
from app.models.user import User
from app.models.workspace import Task
from app.settings import get_settings


def _write_stub_claude(bin_dir):
    """A fake claude CLI that creates a file unique to its worktree, so each run has a distinct diff."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "if '--version' in args:\n"
        "    print('1.2.3 (Claude Code stub)')\n"
        "    sys.exit(0)\n"
        "name = os.path.basename(os.getcwd())\n"
        "with open(f'file_{name}.txt', 'w') as fh:\n"
        "    fh.write('one line\\n')\n"
        "print(json.dumps({\n"
        "    'type': 'result', 'subtype': 'success', 'is_error': False,\n"
        "    'result': 'done', 'total_cost_usd': 0.001,\n"
        "    'usage': {'input_tokens': 3, 'output_tokens': 2}}))\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture()
def loop_env(tmp_path, monkeypatch):
    """Roots, the stub backend, the Anthropic key, and the orchestrator flag on for the loop."""
    settings = get_settings()
    monkeypatch.setattr(settings, "nexa_projects_root", str(tmp_path / "projects"))
    monkeypatch.setattr(settings, "nexa_runtime_root", str(tmp_path / "runtime"))
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-orchestrator")
    monkeypatch.setattr(settings, "nexa_enable_orchestrator", True)
    _write_stub_claude(tmp_path / "bin")
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}")
    return tmp_path


def _user(db):
    user = User(email="loop@example.com", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _project(db, *, slug, default="green", stage="approved"):
    project = Project(
        name="Loop App",
        slug=slug,
        stage=stage,
        mode="app",
        agent_autonomy_default=default,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _task(db, project, *, key, title, sequence, depends_on=None, autonomy="green", user_id=None):
    task = Task(
        user_id=user_id,
        project_id=project.id,
        title=title,
        status="todo",
        source="plan",
        autonomy=autonomy,
        sequence=sequence,
        position=sequence,
        plan_unit_key=key,
        depends_on=depends_on or [],
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _status_by_key(db, project):
    rows = (
        db.query(Task)
        .filter(Task.project_id == project.id, Task.plan_unit_key.isnot(None))
        .all()
    )
    return {t.plan_unit_key: t.status for t in rows}


# --- a green only graph runs to completion unattended -------------------------------------


def test_green_only_graph_runs_to_completion(loop_env, db_session):
    project = _project(db_session, slug="green-graph", default="green")
    a = _task(db_session, project, key="a", title="Step A", sequence=1)
    b = _task(db_session, project, key="b", title="Step B", sequence=2, depends_on=[a.id])
    _task(db_session, project, key="c", title="Step C", sequence=3, depends_on=[b.id])

    state = orchestrate_project(db_session, project)

    assert state["status"] == "completed"
    assert state["runs_dispatched"] == 3
    # Every task merged unattended and landed at review.
    assert _status_by_key(db_session, project) == {"a": "review", "b": "review", "c": "review"}
    # The loop recorded a dispatch and a gate decision per task.
    assert len(state["dispatches"]) == 3
    assert all(d["merged"] for d in state["dispatches"])


# --- a yellow node pauses its branch, a human approve resumes it --------------------------


def test_yellow_node_pauses_branch_then_human_approve_resumes(loop_env, db_session):
    project = _project(db_session, slug="yellow-graph", default="green")
    a = _task(db_session, project, key="a", title="Step A", sequence=1)
    # B is set yellow, so it parks at the gate even though its change is benign.
    b = _task(
        db_session, project, key="b", title="Step B", sequence=2, depends_on=[a.id], autonomy="yellow"
    )
    _task(db_session, project, key="c", title="Step C", sequence=3, depends_on=[b.id])

    state = orchestrate_project(db_session, project)

    # A merged, B parked at the gate, C blocked behind B. The loop is blocked, not complete.
    assert state["status"] == "blocked"
    statuses = _status_by_key(db_session, project)
    assert statuses["a"] == "review"
    assert statuses["b"] == "agent_working"
    assert statuses["c"] == "todo"
    assert any(p["reason"] == "yellow_gate" for p in state["pauses"])

    # A human approves B's parked run.
    db_session.refresh(b)
    run = db_session.get(AgentRun, b.run_id)
    approve_build_run(db_session, run, resolved_by="loop@example.com")
    assert run.phase == PHASE_MERGED

    # Resuming the loop now advances to C, which was blocked behind B.
    state = orchestrate_project(db_session, project)
    assert state["status"] == "completed"
    assert _status_by_key(db_session, project) == {"a": "review", "b": "review", "c": "review"}


# --- a red node never auto runs -----------------------------------------------------------


def test_red_node_never_auto_runs(loop_env, db_session):
    project = _project(db_session, slug="red-graph", default="green")
    _task(db_session, project, key="r", title="Step R", sequence=1, autonomy="red")

    state = orchestrate_project(db_session, project)

    # The red task was dispatched but parked at the gate: it never merged on its own.
    assert state["status"] == "blocked"
    assert _status_by_key(db_session, project) == {"r": "agent_working"}
    assert all(not d["merged"] for d in state["dispatches"])
    assert any(p["reason"] == "red_gate" for p in state["pauses"])


# --- the kill switch refuses dispatch -----------------------------------------------------


def test_kill_switch_refuses_dispatch(loop_env, db_session):
    project = _project(db_session, slug="kill-graph", default="green")
    _task(db_session, project, key="a", title="Step A", sequence=1)
    project.agent_kill_switch = True
    db_session.commit()

    with pytest.raises(OrchestratorHaltedError):
        orchestrate_project(db_session, project)

    # Nothing was dispatched: the task is still todo.
    assert _status_by_key(db_session, project) == {"a": "todo"}


# --- an unapproved project is refused -----------------------------------------------------


def test_unapproved_project_is_refused(loop_env, db_session):
    project = _project(db_session, slug="unapproved-graph", default="green", stage="process")
    _task(db_session, project, key="a", title="Step A", sequence=1)

    with pytest.raises(OrchestratorNotApprovedError):
        orchestrate_project(db_session, project)
    assert _status_by_key(db_session, project) == {"a": "todo"}


# --- the run cap stops the loop -----------------------------------------------------------


def test_run_cap_stops_the_loop(loop_env, db_session):
    project = _project(db_session, slug="cap-graph", default="green")
    _task(db_session, project, key="a", title="Step A", sequence=1)
    _task(db_session, project, key="b", title="Step B", sequence=2)

    state = orchestrate_project(db_session, project, run_cap=1)

    assert state["stopped_reason"] == "run_cap"
    assert state["status"] == "paused"
    statuses = _status_by_key(db_session, project)
    # Exactly one task ran; the other is still waiting.
    assert sorted(statuses.values()) == ["review", "todo"]


# --- the time budget stops the loop -------------------------------------------------------


def test_time_budget_stops_the_loop(loop_env, db_session):
    project = _project(db_session, slug="budget-graph", default="green")
    _task(db_session, project, key="a", title="Step A", sequence=1)

    state = orchestrate_project(db_session, project, budget_seconds=0)

    assert state["stopped_reason"] == "time_budget"
    assert state["status"] == "paused"
    # The budget was spent before any dispatch.
    assert _status_by_key(db_session, project) == {"a": "todo"}


# --- the flag gates dispatch --------------------------------------------------------------


def test_loop_refused_when_flag_off(loop_env, db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_enable_orchestrator", False)
    project = _project(db_session, slug="flagoff-graph", default="green")
    _task(db_session, project, key="a", title="Step A", sequence=1)
    with pytest.raises(OrchestratorDisabledError):
        orchestrate_project(db_session, project)


# --- pause refuses the next run -----------------------------------------------------------


def test_pause_refuses_the_next_run(loop_env, db_session):
    from app.agents.orchestrator import OrchestratorPausedError

    project = _project(db_session, slug="pause-graph", default="green")
    _task(db_session, project, key="a", title="Step A", sequence=1)
    pause_loop(db_session, project)
    with pytest.raises(OrchestratorPausedError):
        orchestrate_project(db_session, project)
    assert _status_by_key(db_session, project) == {"a": "todo"}


# --- force push is still refused ----------------------------------------------------------


def test_force_push_is_still_refused(loop_env, db_session):
    project = _project(db_session, slug="force-graph", default="green")
    ws = prepare_workspace(project)
    with pytest.raises(CommandRefused):
        run_in_workspace(ws, "git push --force origin work")
    with pytest.raises(CommandRefused):
        run_in_workspace(ws, "git push origin main")


# --- the state read reflects progress -----------------------------------------------------


def test_orchestration_state_reports_progress(loop_env, db_session):
    project = _project(db_session, slug="state-graph", default="green")
    _task(db_session, project, key="a", title="Step A", sequence=1)
    orchestrate_project(db_session, project)
    state = orchestration_state(db_session, project)
    assert state["enabled"] is True
    assert state["approved"] is True
    assert state["status"] == "completed"
    assert state["count"] == 1
    assert state["tasks"][0]["status"] == "review"


# --- the HTTP surface ---------------------------------------------------------------------


def _bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    return {"Authorization": "Bearer t"}


def test_endpoint_orchestrates_and_reads_state(loop_env, client, db_session, monkeypatch):
    headers = _bearer(monkeypatch)
    _user(db_session)
    project = _project(db_session, slug="http-graph", default="green")
    _task(db_session, project, key="a", title="Step A", sequence=1)

    res = client.post(f"/agents/projects/{project.id}/orchestrate", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "completed"

    got = client.get(f"/agents/projects/{project.id}/orchestration", headers=headers)
    assert got.status_code == 200
    assert got.json()["runs_dispatched"] == 1


def test_endpoint_refused_when_flag_off(loop_env, client, db_session, monkeypatch):
    headers = _bearer(monkeypatch)
    monkeypatch.setattr(get_settings(), "nexa_enable_orchestrator", False)
    _user(db_session)
    project = _project(db_session, slug="http-flagoff", default="green")
    _task(db_session, project, key="a", title="Step A", sequence=1)
    res = client.post(f"/agents/projects/{project.id}/orchestrate", headers=headers)
    assert res.status_code == 403


def test_endpoint_refused_when_unapproved(loop_env, client, db_session, monkeypatch):
    headers = _bearer(monkeypatch)
    _user(db_session)
    project = _project(db_session, slug="http-unapproved", default="green", stage="process")
    _task(db_session, project, key="a", title="Step A", sequence=1)
    res = client.post(f"/agents/projects/{project.id}/orchestrate", headers=headers)
    assert res.status_code == 409


def test_endpoint_pause_and_resume_round_trip(loop_env, client, db_session, monkeypatch):
    headers = _bearer(monkeypatch)
    _user(db_session)
    project = _project(db_session, slug="http-pause", default="green")
    _task(db_session, project, key="a", title="Step A", sequence=1)

    paused = client.post(f"/agents/projects/{project.id}/pause", headers=headers)
    assert paused.status_code == 200 and paused.json()["status"] == "paused"
    # While paused, orchestrate is refused.
    assert client.post(f"/agents/projects/{project.id}/orchestrate", headers=headers).status_code == 409
    # Resume clears the pause and the loop can run.
    resumed = client.post(f"/agents/projects/{project.id}/resume", headers=headers)
    assert resumed.status_code == 200
    assert client.post(f"/agents/projects/{project.id}/orchestrate", headers=headers).status_code == 200
