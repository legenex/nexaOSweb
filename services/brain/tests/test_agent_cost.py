"""Per run usage and the project cost rollup.

A build run records its cost and token usage as the backend reports it: the cost is denormalised on
the run, the token counts live on the build step's tool evidence. These tests drive the real stub
backed build path and prove the usage is recorded non-null and surfaced, that the project cost
rollup sums it by backend, that a backend over its cost ceiling is skipped with a reason and an
audit row, and that a budget breach pauses dispatch with an audit row.
"""

import stat

import pytest

from app.agents.build_engine import run_usage, start_build_run
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
