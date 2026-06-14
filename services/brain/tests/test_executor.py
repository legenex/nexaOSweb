"""Executor phase a: isolated branch and plan, refused when readiness is not satisfied."""

import subprocess
from pathlib import Path

import pytest

from app.agents.executor import (
    EDIT_STEP_KIND,
    EXECUTOR_KIND,
    PHASE_PLAN,
    PLAN_STEP_KIND,
    ExecutorError,
    ReadinessNotSatisfiedError,
    execute_planned_edits,
    plan_steps_from_requirements,
    start_executor_run,
)
from app.agents.readiness import evaluate_readiness, readiness_satisfied
from app.models.project import BuildLogEntry, Project
from app.models.runtime import AgentRun, AgentStep
from app.runtime import COMPLETED_VERIFIED, PLANNED
from app.safety import PathSafetyError
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


# --- phase b: the gated edit loop ---------------------------------------------------------


def _fixed_synth(content, summary="edit"):
    """A deterministic editor: the same intended content regardless of the prompt."""

    def synth(key, prompt, schema=None):
        return {"new_content": content, "change_summary": summary}

    return synth


def _started_run(db, monkeypatch, tmp_path, slug):
    _roots(monkeypatch, tmp_path)
    project = _project_with_requirements(db, tmp_path, slug=slug)
    readiness = evaluate_readiness(db, plan={}, project_id=project.id)
    run = start_executor_run(db, readiness_run=readiness, project_id=project.id)
    return project, run


def _edit_steps(db, run):
    return (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run.id, AgentStep.kind == EDIT_STEP_KIND)
        .all()
    )


def test_edit_lands_in_worktree_not_checkout(db_session, monkeypatch, tmp_path):
    project, run = _started_run(db_session, monkeypatch, tmp_path, "edit1")
    content = "print('hello')\n"

    steps = execute_planned_edits(
        db_session,
        run,
        [{"file_path": "app/main.py", "instruction": "create the entrypoint"}],
        synthesize=_fixed_synth(content),
    )

    # One edit-kind step, completed_verified from its tool sourced write evidence.
    assert len(steps) == 1
    assert steps[0].kind == EDIT_STEP_KIND
    assert steps[0].status == COMPLETED_VERIFIED

    # The file lands inside the worktree, with the intended content.
    worktree = Path(run.worktree_path)
    assert (worktree / "app" / "main.py").read_text(encoding="utf-8") == content

    # The live checkout never received it.
    source = Path(tmp_path) / "projects" / project.slug
    assert not (source / "app" / "main.py").exists()

    # An applied build log entry backs the change, holding the before (none) and after content.
    entry = (
        db_session.query(BuildLogEntry)
        .filter(BuildLogEntry.project_id == project.id, BuildLogEntry.action == "edit")
        .one()
    )
    assert entry.status == "applied"
    assert entry.before_content is None
    assert entry.after_content == content


def test_rerun_does_not_double_apply(db_session, monkeypatch, tmp_path):
    project, run = _started_run(db_session, monkeypatch, tmp_path, "edit2")
    content = "VALUE = 1\n"
    change = {"file_path": "config.py", "instruction": "set the value"}

    first = execute_planned_edits(db_session, run, [change], synthesize=_fixed_synth(content))
    second = execute_planned_edits(db_session, run, [change], synthesize=_fixed_synth(content))

    # The re-run is a no-op: the same step is returned, with no second step and no second entry.
    assert second[0].id == first[0].id
    assert len(_edit_steps(db_session, run)) == 1
    entries = (
        db_session.query(BuildLogEntry)
        .filter(BuildLogEntry.project_id == project.id, BuildLogEntry.action == "edit")
        .all()
    )
    assert len(entries) == 1
    assert (Path(run.worktree_path) / "config.py").read_text(encoding="utf-8") == content


def test_apply_is_noop_when_target_already_matches(db_session, monkeypatch, tmp_path):
    project, run = _started_run(db_session, monkeypatch, tmp_path, "edit3")
    content = "ready\n"
    # The worktree already holds exactly the intended content before the edit runs.
    (Path(run.worktree_path) / "status.txt").write_text(content, encoding="utf-8")

    steps = execute_planned_edits(
        db_session,
        run,
        [{"file_path": "status.txt", "instruction": "ensure the marker"}],
        synthesize=_fixed_synth(content),
    )

    # The step completes, but no write happened because the content was already present.
    assert steps[0].status == COMPLETED_VERIFIED
    assert steps[0].evidence[0]["wrote"] is False
    entry = (
        db_session.query(BuildLogEntry)
        .filter(BuildLogEntry.project_id == project.id, BuildLogEntry.action == "edit")
        .one()
    )
    assert entry.status == "applied"


def test_live_checkout_is_untouched(db_session, monkeypatch, tmp_path):
    project, run = _started_run(db_session, monkeypatch, tmp_path, "edit4")
    source = Path(tmp_path) / "projects" / project.slug
    head_before = _git(source, "rev-parse", "HEAD").strip()

    execute_planned_edits(
        db_session,
        run,
        [{"file_path": "new.txt", "instruction": "add a file"}],
        synthesize=_fixed_synth("data\n"),
    )

    # The live checkout is clean, its HEAD is unmoved, and it never received the new file.
    assert _git(source, "status", "--porcelain").strip() == ""
    assert _git(source, "rev-parse", "HEAD").strip() == head_before
    assert not (source / "new.txt").exists()


def test_edit_refused_on_protected_branch(db_session, monkeypatch, tmp_path):
    _project, run = _started_run(db_session, monkeypatch, tmp_path, "edit5")
    run.branch_ref = "main"
    db_session.commit()

    with pytest.raises(ExecutorError):
        execute_planned_edits(
            db_session,
            run,
            [{"file_path": "x.txt", "instruction": "y"}],
            synthesize=_fixed_synth("z"),
        )


def test_edit_path_escape_is_blocked(db_session, monkeypatch, tmp_path):
    _project, run = _started_run(db_session, monkeypatch, tmp_path, "edit6")

    with pytest.raises(PathSafetyError):
        execute_planned_edits(
            db_session,
            run,
            [{"file_path": "../escape.txt", "instruction": "escape"}],
            synthesize=_fixed_synth("x"),
        )

    # Nothing escaped: no file was written beside the worktree.
    assert not (Path(run.worktree_path).parent / "escape.txt").exists()
