"""The Grok Build adapter behind the same AgentBackend interface, gated by NEXA_ENABLE_GROK.

These tests prove the feature flagged third backend without a network call or a real Grok install. A
stub grok CLI is placed on PATH that answers the version probe and, on a headless run, creates
README.md in its working directory and prints the json result the real CLI would. The adapter then
captures that into an AgentResult, exactly as it does for Claude Code and Codex.

The acceptance is checked directly:

  - With the flag off, Grok is absent from selection (not in available_backends, get_backend refuses
    it, and a run is refused) and the health probe reports it disabled and not available.
  - With the flag on and a key present, the health probe reports available and the same trivial task
    from AB1.2 runs through the adapter and returns a diff that adds the file, inside the workspace
    and nowhere else, with no provider key in the prompt or the result.
"""

import json
import os
import stat

import pytest

from app.engine import (
    AgentResult,
    BackendError,
    GrokBuildBackend,
    available_backends,
    get_backend,
    prepare_workspace,
)
from app.models.project import Project
from app.settings import get_settings

_API_KEY = "xai-should-never-leak"


def _write_stub_grok(bin_dir, *, marker_path):
    """Install a fake grok CLI that answers --version and, on a headless run, creates README.md.

    The stub writes the prompt it received and whether the xAI key was in its environment to a marker
    file, so a test can prove the task reached the CLI as the prompt and the key reached it only
    through the environment, never through the prompt text.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "grok"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "if '--version' in args:\n"
        "    print('grok-build 0.4.1 (stub)')\n"
        "    sys.exit(0)\n"
        "prompt = ''\n"
        "if '-p' in args:\n"
        "    i = args.index('-p')\n"
        "    if i + 1 < len(args):\n"
        "        prompt = args[i + 1]\n"
        "seen = {'prompt': prompt, 'key_in_env': os.environ.get('XAI_API_KEY', '')}\n"
        f"open({marker_path!r}, 'w').write(json.dumps(seen))\n"
        "with open('README.md', 'w') as fh:\n"
        "    fh.write('one line\\n')\n"
        "print(json.dumps({\n"
        "    'type': 'result', 'subtype': 'success', 'is_error': False,\n"
        "    'result': 'Created README.md with one line.',\n"
        "    'total_cost_usd': 0.0009,\n"
        "    'usage': {'input_tokens': 13, 'output_tokens': 5},\n"
        "}))\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script


@pytest.fixture()
def builds(tmp_path, monkeypatch):
    """Point the builds root at a throwaway directory and configure the xAI key. The Grok flag is
    left at its default (off) so each test sets it explicitly to the state it exercises."""
    monkeypatch.setattr(get_settings(), "nexa_runtime_root", str(tmp_path / "builds"))
    monkeypatch.setattr(get_settings(), "xai_api_key", _API_KEY)
    return tmp_path


@pytest.fixture()
def stub_on_path(tmp_path, monkeypatch):
    """Install the stub grok CLI and prepend it to PATH for the duration of the test."""
    marker = tmp_path / "cli_marker.json"
    _write_stub_grok(tmp_path / "bin", marker_path=str(marker))
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}")
    return marker


def _enable(monkeypatch, on=True):
    monkeypatch.setattr(get_settings(), "nexa_enable_grok", on)


def _project(slug="readme-app-grok"):
    return Project(name="Readme App", slug=slug)


# --- flag off: absent from selection, health reports disabled -----------------------------


def test_flag_off_grok_absent_from_selection(builds, monkeypatch):
    _enable(monkeypatch, on=False)
    assert "grok-build" not in available_backends()
    # claude-code and codex-cli are still selectable; only the flagged backend is hidden.
    assert "claude-code" in available_backends()
    assert "codex-cli" in available_backends()


def test_flag_off_get_backend_refuses_grok(builds, monkeypatch):
    _enable(monkeypatch, on=False)
    with pytest.raises(BackendError):
        get_backend("grok-build")


def test_flag_off_health_reports_disabled(builds, stub_on_path, monkeypatch):
    _enable(monkeypatch, on=False)
    health = GrokBuildBackend().health()
    assert not health.enabled
    assert not health.available
    assert "disabled" in health.detail.lower()
    # A disabled backend never shells out to probe a CLI.
    assert not health.installed


def test_flag_off_run_is_refused(builds, stub_on_path, monkeypatch):
    _enable(monkeypatch, on=False)
    ws = prepare_workspace(_project(slug="disabled-app-grok"))
    with pytest.raises(BackendError):
        GrokBuildBackend().run("Create README.md with one line.", ws, timeout=60)


# --- flag on: selectable, healthy, runs ---------------------------------------------------


def test_flag_on_grok_is_selectable(builds, monkeypatch):
    _enable(monkeypatch, on=True)
    assert "grok-build" in available_backends()
    backend = get_backend("grok-build")
    assert isinstance(backend, GrokBuildBackend)
    assert backend.name == "grok-build"


def test_flag_on_health_reports_available(builds, stub_on_path, monkeypatch):
    _enable(monkeypatch, on=True)
    health = GrokBuildBackend().health()
    assert health.enabled
    assert health.installed
    assert health.authed
    assert health.available
    assert "0.4.1" in health.detail


def test_flag_on_health_unauthed_when_key_absent(stub_on_path, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_runtime_root", str(tmp_path / "builds"))
    monkeypatch.setattr(get_settings(), "xai_api_key", "")
    monkeypatch.setattr(get_settings(), "nexa_enable_grok", True)
    health = GrokBuildBackend().health()
    assert health.enabled
    assert health.installed
    assert not health.authed
    assert not health.available


def test_flag_on_run_trivial_task_returns_a_diff_that_adds_the_file(builds, stub_on_path, monkeypatch):
    _enable(monkeypatch, on=True)
    ws = prepare_workspace(_project())
    result = GrokBuildBackend().run(
        "Create README.md with one line.", ws, autonomy=1, timeout=60
    )

    assert isinstance(result, AgentResult)
    assert result.ok
    assert result.exit_code == 0
    assert not result.timed_out
    assert result.backend == "grok-build"

    # The diff adds README.md with the one line.
    assert "README.md" in result.diff
    assert "+one line" in result.diff
    assert "README.md" in result.files_changed

    # The reasoning and the cost estimate were parsed out of the CLI json.
    assert "README.md" in result.reasoning
    assert result.cost_usd == pytest.approx(0.0009)
    assert result.input_tokens == 13
    assert result.output_tokens == 5


def test_flag_on_run_writes_only_inside_the_workspace(builds, stub_on_path, monkeypatch):
    from app.engine import builds_root

    _enable(monkeypatch, on=True)
    ws = prepare_workspace(_project(slug="confined-app-grok"))
    before = {p.name for p in builds_root().iterdir()}

    GrokBuildBackend().run("Create README.md with one line.", ws, autonomy=1, timeout=60)

    assert (ws.path / "README.md").read_text(encoding="utf-8") == "one line\n"
    after = {p.name for p in builds_root().iterdir()}
    assert after == before
    assert before == {"confined-app-grok"}


def test_flag_on_provider_key_never_enters_the_prompt_or_the_result(builds, stub_on_path, monkeypatch):
    _enable(monkeypatch, on=True)
    ws = prepare_workspace(_project(slug="secret-app-grok"))
    result = GrokBuildBackend().run(
        "Create README.md with one line.", ws, context="Project requirements here.", timeout=60
    )

    assert _API_KEY not in result.diff
    assert _API_KEY not in result.transcript
    assert _API_KEY not in result.reasoning

    marker = json.loads(stub_on_path.read_text(encoding="utf-8"))
    assert "Create README.md with one line." in marker["prompt"]
    assert _API_KEY not in marker["prompt"]
    assert marker["key_in_env"] == _API_KEY
