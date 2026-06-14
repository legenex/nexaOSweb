"""Executor phase a: isolated branch and plan, refused when readiness is not satisfied."""

import subprocess
from pathlib import Path

import pytest

from app.agents.executor import (
    EXECUTOR_KIND,
    PHASE_PLAN,
    PLAN_STEP_KIND,
    ReadinessNotSatisfiedError,
    plan_steps_from_requirements,
    start_executor_run,
)
from app.agents.readiness import evaluate_readiness, readiness_satisfied
from app.models.project import Project
from app.models.runtime import AgentRun, AgentStep
from app.runtime import PLANNED
from app.settings import get_settings


def _roots(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "nexa_projects_root", str(tmp_path / "projects"))
    monkeypatch.setattr(settings, "nexa_runtime_root", str(tmp_path / "runtime"))


_DEFAULT_BODY = "- Build the API\n- Add the UI\n- Write tests\n"


def _project_with_requirements(db, tmp_path, slug="alpha", body=_DEFAULT_BODY):
    project = Project(name="Alpha", slug=slug, stage="build")
    db.add(project)
    db.commit()
    db.refresh(project)
    reqs_dir = Path(tmp_path) / "projects" / slug
    reqs_dir.mkdir(parents=True)
    (reqs_dir / "requirements.md").write_text(f"# Requirements\n\n{body}", encoding="utf-8")
    return project


def _steps(db, run):
    return (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run.id)
        .order_by(AgentStep.seq.asc())
        .all()
    )


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True
    ).stdout


def test_phase_a_creates_worktree_branch_and_plan_with_no_edits(db_session, monkeypatch, tmp_path):
    _roots(monkeypatch, tmp_path)
    project = _project_with_requirements(db_session, tmp_path)

    # An empty plan has no blocking items, so readiness is satisfied and the run may start.
    readiness = evaluate_readiness(db_session, plan={}, project_id=project.id)
    assert readiness_satisfied(db_session, readiness)

    run = start_executor_run(db_session, readiness_run=readiness, project_id=project.id)

    # The run is an executor-kind AgentRun on the existing spine, linked to its readiness run.
    assert run.kind == EXECUTOR_KIND
    assert run.parent_run_id == readiness.id
    assert run.phase == PHASE_PLAN
    assert run.branch_ref == f"executor/run-{run.id}"

    # The isolated worktree exists under the runtime root, on the recorded branch.
    worktree = Path(run.worktree_path)
    assert worktree.is_dir()
    assert str(worktree).startswith(str(Path(tmp_path) / "runtime"))
    assert (worktree / ".git").exists()
    assert run.branch_ref in _git(worktree, "branch", "--show-current")

    # The plan is persisted as ordered plan-kind steps with per-run idempotency keys, at planned.
    steps = _steps(db_session, run)
    assert [s.title for s in steps] == ["Build the API", "Add the UI", "Write tests"]
    assert all(s.kind == PLAN_STEP_KIND for s in steps)
    assert all(s.status == PLANNED for s in steps)
    assert [s.idempotency_key for s in steps] == ["plan:0", "plan:1", "plan:2"]

    # No edits: the worktree is clean and the branch carries no commit beyond the baseline.
    assert _git(worktree, "status", "--porcelain").strip() == ""
    source = Path(tmp_path) / "projects" / project.slug
    assert _git(worktree, "rev-parse", "HEAD").strip() == _git(source, "rev-parse", "HEAD").strip()


def test_idempotency_key_is_unique_per_run(db_session, monkeypatch, tmp_path):
    _roots(monkeypatch, tmp_path)
    project = _project_with_requirements(db_session, tmp_path, slug="beta")
    readiness = evaluate_readiness(db_session, plan={}, project_id=project.id)

    run = start_executor_run(db_session, readiness_run=readiness, project_id=project.id)
    keys = [s.idempotency_key for s in _steps(db_session, run)]
    assert len(keys) == len(set(keys))


def test_run_is_refused_when_readiness_is_not_satisfied(db_session, monkeypatch, tmp_path):
    _roots(monkeypatch, tmp_path)
    project = _project_with_requirements(db_session, tmp_path, slug="gamma")

    # A blocking decision no source can answer leaves a gate open, so readiness is not satisfied.
    plan = {
        "requirements": [
            {"key": "database", "question": "Which database?", "kind": "decision", "blocking": True}
        ]
    }
    readiness = evaluate_readiness(db_session, plan=plan, project_id=project.id)
    assert not readiness_satisfied(db_session, readiness)

    with pytest.raises(ReadinessNotSatisfiedError):
        start_executor_run(db_session, readiness_run=readiness, project_id=project.id)

    # Nothing was created: no executor run and no worktree.
    assert db_session.query(AgentRun).filter(AgentRun.kind == EXECUTOR_KIND).count() == 0
    worktrees = Path(tmp_path) / "runtime" / "worktrees"
    assert not worktrees.exists() or not any(worktrees.iterdir())


def test_plan_falls_back_to_headings_then_a_single_step():
    headings = plan_steps_from_requirements("# Requirements\n\n## Backend\n\n## Frontend\n")
    assert [s["title"] for s in headings] == ["Backend", "Frontend"]

    bare = plan_steps_from_requirements("# Requirements\n\nJust some prose, no tasks.\n")
    assert [s["title"] for s in bare] == ["Implement the approved requirements"]
