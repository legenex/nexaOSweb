"""The Agent Build Engine: one gated build run on the executor spine, proven end to end.

These tests drive a real claude-code backend (a stub CLI on PATH that creates README.md, so no
network and no real install is needed) through the build engine: a run starts, the agent edits the
executor's worktree, the diff is captured and parked at the human gate, approve promotes the diff
into the served project repo through the executor merge; reject discards it and restores the task.
Bad input, an unavailable backend, a workspace escape, and a force push are all still refused.
"""

import stat
from pathlib import Path

import pytest

from app.agents.build_engine import (
    BUILD_STEP_KIND,
    PHASE_CANCELLED,
    PHASE_REJECTED,
    BackendUnavailableError,
    BuildEngineError,
    approve_build_run,
    build_run_detail,
    cancel_build_run,
    reject_build_run,
    start_build_run,
)
from app.agents.executor import MERGE_STEP_KIND, PHASE_MERGED
from app.engine import CommandRefused, builds_root, prepare_workspace, run_in_workspace
from app.models.project import Project
from app.models.runtime import AgentStep
from app.models.user import User
from app.models.workspace import Task
from app.runtime import RUN_WAITING_APPROVAL
from app.settings import get_settings

_API_KEY = "sk-ant-build-should-never-leak"


def _write_stub_claude(bin_dir):
    """A fake claude CLI: answers --version and, on a headless run, creates README.md in the cwd."""
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
    return script


@pytest.fixture()
def roots(tmp_path, monkeypatch):
    """Point the projects root and the single agent execution root at throwaway directories."""
    settings = get_settings()
    monkeypatch.setattr(settings, "nexa_projects_root", str(tmp_path / "projects"))
    monkeypatch.setattr(settings, "nexa_runtime_root", str(tmp_path / "runtime"))
    return tmp_path


@pytest.fixture()
def stub_backend(tmp_path, monkeypatch):
    """Install the stub claude CLI on PATH and configure the Anthropic key, server side."""
    import os

    _write_stub_claude(tmp_path / "bin")
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", _API_KEY)


def _user(db):
    user = User(email="builder@example.com", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _project(db, slug="builder-app"):
    project = Project(name="Builder App", slug=slug, stage="build", mode="app")
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


# --- the gated loop -----------------------------------------------------------------------


def test_start_captures_a_diff_and_parks_at_the_gate(db_session, roots, stub_backend):
    user = _user(db_session)
    project = _project(db_session)
    task = _task(db_session, user, project)

    run = start_build_run(db_session, task=task, proposed_by="builder@example.com")

    # The run is a build run on the executor spine, parked at the human gate.
    assert run.backend == "claude-code"
    assert run.kind == "executor"
    assert run.task_id == task.id
    assert run.status == RUN_WAITING_APPROVAL

    # The task flipped to agent_working and links the run.
    db_session.refresh(task)
    assert task.status == "agent_working"
    assert task.run_id == run.id

    # The agent's work and the diff are both recorded; the diff adds README.md.
    build_step = (
        db_session.query(AgentStep)
        .filter(AgentStep.run_id == run.id, AgentStep.kind == BUILD_STEP_KIND)
        .one()
    )
    assert build_step.status == "completed_verified"
    detail = build_run_detail(db_session, run)
    assert "README.md" in detail["diff"]
    assert "+one line" in detail["diff"]
    assert "README.md" in detail["files_changed"]
    assert detail["reasoning_summary"] == "Created README.md with one line."
    assert detail["cost_usd"] == pytest.approx(0.0012)
    assert detail["gate_step_id"] is not None


def test_secrets_never_leak_into_the_run(db_session, roots, stub_backend):
    user = _user(db_session)
    project = _project(db_session)
    task = _task(db_session, user, project)

    run = start_build_run(db_session, task=task)
    detail = build_run_detail(db_session, run)
    assert _API_KEY not in detail["diff"]
    assert _API_KEY not in detail["transcript"]
    assert _API_KEY not in (detail["reasoning_summary"] or "")


def test_approve_merges_the_diff_into_the_served_project(db_session, roots, stub_backend):
    user = _user(db_session)
    project = _project(db_session)
    task = _task(db_session, user, project)

    run = start_build_run(db_session, task=task)
    run = approve_build_run(db_session, run, resolved_by="builder@example.com")

    # The merge ran through the executor path and promoted README.md into the served folder.
    assert run.phase == PHASE_MERGED
    merge_step = (
        db_session.query(AgentStep)
        .filter(AgentStep.run_id == run.id, AgentStep.kind == MERGE_STEP_KIND)
        .one()
    )
    assert merge_step.status in ("completed_verified", "completed_unverified")
    served = Path(roots) / "projects" / project.slug / "README.md"
    assert served.read_text(encoding="utf-8") == "one line\n"

    # The task moved to review.
    db_session.refresh(task)
    assert task.status == "review"


def test_reject_discards_the_diff_and_restores_the_task(db_session, roots, stub_backend):
    user = _user(db_session)
    project = _project(db_session)
    task = _task(db_session, user, project, status="doing")

    run = start_build_run(db_session, task=task)
    run = reject_build_run(db_session, run, resolved_by="builder@example.com")

    # Nothing merged: the served folder never received README.md.
    assert run.phase == PHASE_REJECTED
    assert not (Path(roots) / "projects" / project.slug / "README.md").exists()
    no_merge = (
        db_session.query(AgentStep)
        .filter(AgentStep.run_id == run.id, AgentStep.kind == MERGE_STEP_KIND)
        .count()
    )
    assert no_merge == 0

    # The task returned to the status it held before the run.
    db_session.refresh(task)
    assert task.status == "doing"


def test_cancel_returns_the_task_to_its_prior_status(db_session, roots, stub_backend):
    user = _user(db_session)
    project = _project(db_session)
    task = _task(db_session, user, project, status="todo")

    run = start_build_run(db_session, task=task)
    run = cancel_build_run(db_session, run, resolved_by="builder@example.com")

    assert run.phase == PHASE_CANCELLED
    db_session.refresh(task)
    assert task.status == "todo"


# --- guards still hold --------------------------------------------------------------------


def test_bad_input_a_task_without_a_project_is_refused(db_session, roots, stub_backend):
    user = _user(db_session)
    task = Task(user_id=user.id, project_id=None, title="orphan", status="todo")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    with pytest.raises(BuildEngineError):
        start_build_run(db_session, task=task)


def test_backend_unavailable_without_the_cli_or_key_is_refused(db_session, roots):
    # No stub on PATH and no key configured: the backend is not available, so the run is refused.
    user = _user(db_session)
    project = _project(db_session)
    task = _task(db_session, user, project)
    with pytest.raises(BackendUnavailableError):
        start_build_run(db_session, task=task)
    # The task was never flipped because the run never started.
    db_session.refresh(task)
    assert task.status == "doing"


def test_workspace_escape_is_still_refused(db_session, roots):
    project = _project(db_session, slug="escape-app")
    ws = prepare_workspace(project)
    assert builds_root() in ws.path.parents  # the single execution root
    with pytest.raises(CommandRefused):
        run_in_workspace(ws, "cat ../../../etc/passwd")


def test_force_push_and_protected_branch_are_still_refused(db_session, roots):
    project = _project(db_session, slug="push-app")
    ws = prepare_workspace(project)
    with pytest.raises(CommandRefused):
        run_in_workspace(ws, "git push --force origin work")
    with pytest.raises(CommandRefused):
        run_in_workspace(ws, "git push origin main")


# --- the HTTP surface ---------------------------------------------------------------------


def test_endpoints_start_review_and_approve(client, db_session, roots, stub_backend, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    bearer = {"Authorization": "Bearer t"}
    user = _user(db_session)  # bearer acts as the earliest user
    project = _project(db_session)
    task = _task(db_session, user, project)

    started = client.post("/agents/runs", json={"task_id": task.id}, headers=bearer)
    assert started.status_code == 201
    run_id = started.json()["id"]
    assert started.json()["status"] == RUN_WAITING_APPROVAL

    got = client.get(f"/agents/runs/{run_id}", headers=bearer)
    assert got.status_code == 200
    assert "README.md" in got.json()["diff"]

    approved = client.post(f"/agents/runs/{run_id}/approve", headers=bearer)
    assert approved.status_code == 200
    assert approved.json()["phase"] == PHASE_MERGED
    served = Path(roots) / "projects" / project.slug / "README.md"
    assert served.read_text(encoding="utf-8") == "one line\n"


def test_start_with_a_missing_task_is_404(client, db_session, roots, stub_backend, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    _user(db_session)
    res = client.post("/agents/runs", json={"task_id": 9999}, headers={"Authorization": "Bearer t"})
    assert res.status_code == 404
