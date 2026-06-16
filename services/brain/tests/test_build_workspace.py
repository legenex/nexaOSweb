"""The Agent Build Engine sandbox: workspace isolation, the guarded runner, and the worker.

These tests prove the safe box before any agent runs in it: a workspace is prepared for a sample
repo under the builds root, a bounded command runs inside it, and a command that tries to leave the
workspace or force push (or push a protected branch) is refused before it reaches the shell.
"""

import subprocess

import pytest

from app.engine import (
    CommandRefused,
    InProcessWorker,
    Job,
    WorkspaceError,
    builds_root,
    get_worker,
    prepare_workspace,
    run_in_workspace,
)
from app.models.project import Project
from app.safety import PathSafetyError
from app.settings import get_settings

_GIT_USER = ("-c", "user.email=test@nexaos.local", "-c", "user.name=nexaOS test")


def _make_source_repo(path):
    """A local git repo with one commit, used as a clone source so no network is touched."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    (path / "README.md").write_text("# Sample\n", encoding="utf-8")
    subprocess.run([*("git",), *_GIT_USER, "add", "-A"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", *_GIT_USER, "commit", "-m", "init"], cwd=str(path), check=True, capture_output=True
    )
    return path


@pytest.fixture()
def builds(tmp_path, monkeypatch):
    """Point the single agent execution root at a throwaway directory for the test."""
    monkeypatch.setattr(get_settings(), "nexa_runtime_root", str(tmp_path / "builds"))
    return tmp_path


def _project(slug="sample-app"):
    return Project(name="Sample App", slug=slug)


def test_prepare_workspace_clones_sample_repo(builds):
    source = _make_source_repo(builds / "source")
    ws = prepare_workspace(_project(), repo_url=str(source))

    # The workspace lives under the builds root and is a real checkout of the sample repo.
    assert builds_root() in ws.path.parents
    assert (ws.path / ".git").is_dir()
    assert (ws.path / "README.md").read_text(encoding="utf-8") == "# Sample\n"


def test_prepare_workspace_inits_fresh_when_no_repo_url(builds):
    ws = prepare_workspace(_project(slug="fresh-app"))
    assert (ws.path / ".git").is_dir()
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"], cwd=str(ws.path), capture_output=True, text=True
    )
    assert head.returncode == 0  # the baseline commit gives a HEAD to branch from


def test_prepare_workspace_is_idempotent(builds):
    source = _make_source_repo(builds / "source")
    first = prepare_workspace(_project(), repo_url=str(source))
    (first.path / "scratch.txt").write_text("kept", encoding="utf-8")
    second = prepare_workspace(_project(), repo_url=str(source))
    # Re-preparing reuses the existing checkout, it does not wipe local work.
    assert second.path == first.path
    assert (second.path / "scratch.txt").read_text(encoding="utf-8") == "kept"


def test_prepare_workspace_refuses_slug_escape(builds):
    with pytest.raises((WorkspaceError, PathSafetyError)):
        prepare_workspace(_project(slug="../escape"))


def test_run_bounded_command_captures_output(builds):
    ws = prepare_workspace(_project(slug="run-app"))
    result = run_in_workspace(ws, "git rev-parse --is-inside-work-tree", timeout=30)
    assert result.ok
    assert result.exit_code == 0
    assert result.stdout.strip() == "true"


def test_run_command_times_out(builds):
    ws = prepare_workspace(_project(slug="slow-app"))
    result = run_in_workspace(ws, ["sleep", "5"], timeout=1)
    assert result.timed_out
    assert result.exit_code is None
    assert not result.ok


def test_command_that_escapes_workspace_is_refused(builds):
    ws = prepare_workspace(_project(slug="escape-app"))
    with pytest.raises(CommandRefused):
        run_in_workspace(ws, "cat ../../../etc/passwd")
    with pytest.raises(CommandRefused):
        run_in_workspace(ws, ["cat", "/etc/hostname"])


def test_force_push_is_refused(builds):
    ws = prepare_workspace(_project(slug="push-app"))
    with pytest.raises(CommandRefused):
        run_in_workspace(ws, "git push --force origin work")
    with pytest.raises(CommandRefused):
        run_in_workspace(ws, "git push -f origin work")


def test_push_to_protected_branch_is_refused(builds):
    ws = prepare_workspace(_project(slug="protected-app"))
    with pytest.raises(CommandRefused):
        run_in_workspace(ws, "git push origin main")
    with pytest.raises(CommandRefused):
        run_in_workspace(ws, "git push origin HEAD:production")


def test_secrets_are_scrubbed_from_the_command_environment(builds, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("NEXA_SESSION_SECRET", "also-secret")
    monkeypatch.setenv("HARMLESS_VALUE", "ok")
    ws = prepare_workspace(_project(slug="env-app"))
    result = run_in_workspace(ws, ["env"], timeout=30)
    assert "sk-should-not-leak" not in result.stdout
    assert "ANTHROPIC_API_KEY" not in result.stdout
    assert "NEXA_SESSION_SECRET" not in result.stdout
    assert "HARMLESS_VALUE=ok" in result.stdout


def test_worker_runs_a_job_in_the_workspace(builds):
    ws = prepare_workspace(_project(slug="worker-app"))
    worker = get_worker()
    assert isinstance(worker, InProcessWorker)

    job = Job(
        name="rev-parse",
        run_id=7,
        run=lambda: run_in_workspace(ws, "git rev-parse --abbrev-ref HEAD", timeout=30),
    )
    result = worker.submit(job)
    assert result.ok
    assert result.run_id == 7
    assert result.value.ok


def test_worker_captures_a_failing_job_as_a_result(builds):
    def boom():
        raise RuntimeError("kaboom")

    result = get_worker().submit(Job(name="boom", run=boom))
    assert not result.ok
    assert "kaboom" in (result.error or "")
