"""The declarative agent backend selector and its policy.

These tests prove selection without any real CLI: the health probe and the selectable set are injected
so the selector can be driven through every branch deterministically. They check the acceptance for
AB3.3 directly:

  - a backend resolves for each task type from config/agents.yaml,
  - the order falls through to the next backend when the preferred one is unhealthy,
  - a manual override is honoured (tried first and chosen when available),
  - a candidate over its cost ceiling is skipped,
  - Grok is only ever chosen when it is in the selectable set (its feature flag on),
  - and a real build run records which backend ran, with the selection trail on the run.
"""

import stat

import pytest

from app.engine import select_backend
from app.engine.backends.base import BackendHealth


def _health(name, *, available=True, enabled=True, installed=True, authed=True, detail=""):
    return BackendHealth(
        backend=name,
        installed=installed if available else installed,
        authed=authed if available else authed,
        enabled=enabled,
        detail=detail,
    )


def _all_available_probe(name):
    """Every backend reports available."""
    return _health(name, installed=True, authed=True, enabled=True)


def _all_three():
    return ["claude-code", "codex-cli", "grok-build"]


# --- a backend resolves for each task type ------------------------------------------------


@pytest.mark.parametrize(
    "task_type,expected",
    [
        ("feature", "claude-code"),
        ("bugfix", "codex-cli"),
        ("refactor", "claude-code"),
        ("docs", "codex-cli"),
        ("research", "claude-code"),
        (None, "claude-code"),  # no type falls to the default policy
        ("unmapped-type", "claude-code"),  # an unknown type falls to the default policy
    ],
)
def test_resolves_a_backend_for_each_task_type(task_type, expected):
    choice = select_backend(
        task_type=task_type,
        available=_all_three,
        probe=_all_available_probe,
    )
    assert choice.backend == expected
    assert choice.order[0] == choice.preferred


def test_a_tag_overrides_the_task_type_policy():
    # The urgent tag policy prefers codex-cli, winning over the feature type's claude-code.
    choice = select_backend(
        task_type="feature",
        tags=["urgent"],
        available=_all_three,
        probe=_all_available_probe,
    )
    assert choice.backend == "codex-cli"
    assert choice.policy_source == "tag:urgent"


# --- falls through when the preferred backend is unhealthy --------------------------------


def test_falls_through_when_preferred_is_unhealthy():
    # feature prefers claude-code; mark it unavailable, so the order falls to codex-cli.
    def probe(name):
        if name == "claude-code":
            return _health(name, available=False, installed=False, detail="claude CLI not found")
        return _all_available_probe(name)

    choice = select_backend(task_type="feature", available=_all_three, probe=probe)
    assert choice.backend == "codex-cli"
    # The trail records claude-code was considered first and skipped, codex-cli chosen.
    first = choice.considered[0]
    assert first["backend"] == "claude-code"
    assert not first["available"]
    assert choice.considered[-1]["backend"] == "codex-cli"
    assert choice.considered[-1]["chosen"]


def test_falls_through_twice_to_the_last_in_the_order():
    # feature order is claude-code, codex-cli, grok-build; only grok is healthy.
    def probe(name):
        if name == "grok-build":
            return _all_available_probe(name)
        return _health(name, available=False, installed=False, detail="unavailable")

    choice = select_backend(task_type="feature", available=_all_three, probe=probe)
    assert choice.backend == "grok-build"


def test_no_backend_available_returns_none():
    def probe(name):
        return _health(name, available=False, installed=False, detail="unavailable")

    choice = select_backend(task_type="feature", available=_all_three, probe=probe)
    assert choice.backend is None
    assert "no backend available" in choice.reason


# --- honours a manual override ------------------------------------------------------------


def test_honours_a_manual_override():
    # feature prefers claude-code; override to codex-cli wins outright when available.
    choice = select_backend(
        task_type="feature",
        override="codex-cli",
        available=_all_three,
        probe=_all_available_probe,
    )
    assert choice.backend == "codex-cli"
    assert choice.policy_source == "override"
    assert choice.override == "codex-cli"
    assert choice.order[0] == "codex-cli"


def test_override_falls_through_when_unavailable():
    # An override that is down does not strand the run: selection falls to the policy order.
    def probe(name):
        if name == "grok-build":
            return _health(name, available=False, enabled=False, detail="Grok Build is disabled")
        return _all_available_probe(name)

    choice = select_backend(
        task_type="feature",
        override="grok-build",
        available=_all_three,
        probe=probe,
    )
    assert choice.backend == "claude-code"
    assert choice.considered[0]["backend"] == "grok-build"
    assert not choice.considered[0]["available"]


# --- cost ceiling -------------------------------------------------------------------------


def test_skips_a_candidate_over_its_cost_ceiling():
    # claude-code's ceiling in agents.yaml is 5.0; an estimate above it is skipped for codex-cli.
    choice = select_backend(
        task_type="feature",
        cost_estimates={"claude-code": 9.99},
        available=_all_three,
        probe=_all_available_probe,
    )
    assert choice.backend == "codex-cli"
    assert choice.considered[0]["backend"] == "claude-code"
    assert choice.considered[0]["over_ceiling"]


def test_within_ceiling_is_kept():
    choice = select_backend(
        task_type="feature",
        cost_estimates={"claude-code": 1.0},
        available=_all_three,
        probe=_all_available_probe,
    )
    assert choice.backend == "claude-code"


# --- Grok only when enabled (in the selectable set) ---------------------------------------


def test_grok_is_skipped_when_not_selectable():
    # The selectable set excludes grok (flag off). bugfix order is codex-cli, claude-code, grok-build;
    # with codex and claude unhealthy, grok must NOT be chosen because it is not selectable.
    def available():
        return ["claude-code", "codex-cli"]

    def probe(name):
        if name in ("codex-cli", "claude-code"):
            return _health(name, available=False, installed=False, detail="unavailable")
        return _all_available_probe(name)

    choice = select_backend(task_type="bugfix", available=available, probe=probe)
    assert choice.backend is None
    grok = [c for c in choice.considered if c["backend"] == "grok-build"][0]
    assert not grok["selectable"]


def test_grok_chosen_when_selectable_and_only_one_healthy():
    def probe(name):
        if name == "grok-build":
            return _all_available_probe(name)
        return _health(name, available=False, installed=False, detail="unavailable")

    choice = select_backend(task_type="bugfix", available=_all_three, probe=probe)
    assert choice.backend == "grok-build"


# --- the run records which backend ran ----------------------------------------------------


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
        "print(json.dumps({'type': 'result', 'result': 'done', 'total_cost_usd': 0.001,\n"
        "    'usage': {'input_tokens': 3, 'output_tokens': 2}}))\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def test_a_real_run_records_the_chosen_backend_and_the_selection(db_session, tmp_path, monkeypatch):
    import os

    from app.agents.build_engine import start_build_run
    from app.models.project import Project
    from app.models.user import User
    from app.models.workspace import Task
    from app.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "nexa_projects_root", str(tmp_path / "projects"))
    monkeypatch.setattr(settings, "nexa_runtime_root", str(tmp_path / "runtime"))
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    _write_stub_claude(tmp_path / "bin")
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}")

    user = User(email="sel@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    project = Project(name="Sel App", slug="sel-app", stage="build", mode="app")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    task = Task(
        user_id=user.id,
        project_id=project.id,
        title="Create README.md",
        status="doing",
        source="manual",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    run = start_build_run(db_session, task=task, proposed_by="sel@example.com")

    # The run records which backend ran and the selection trail that chose it.
    assert run.backend == "claude-code"
    selection = run.plan["build"]["selection"]
    assert selection["preferred"] == "claude-code"
    assert selection["policy_source"] == "default"
    assert run.plan["build"]["backend"] == "claude-code"
    assert any(c["chosen"] and c["backend"] == "claude-code" for c in selection["considered"])
