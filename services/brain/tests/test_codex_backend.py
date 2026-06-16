"""The Codex CLI adapter behind the same AgentBackend interface as Claude Code.

These tests prove the second backend without a network call or a real Codex install: a stub codex CLI
is placed on PATH that answers the version probe and, on a non interactive exec run, creates README.md
in its working directory and prints the JSONL event stream the real CLI would. The adapter then
captures that into an AgentResult, exactly as it does for Claude Code.

The acceptance is checked directly, the same trivial task as AB1.2: the health probe reports the
backend available, "create README.md with one line" run in a sandbox workspace returns a diff that
adds that file, the file lands inside the workspace and nowhere else, and no provider key leaks into
the prompt or the result.
"""

import json
import os
import stat

import pytest

from app.engine import (
    AgentResult,
    BackendError,
    CodexCliBackend,
    available_backends,
    get_backend,
    prepare_workspace,
)
from app.models.project import Project
from app.settings import get_settings

_API_KEY = "sk-openai-should-never-leak"


def _write_stub_codex(bin_dir, *, marker_path):
    """Install a fake codex CLI that answers --version and, on an exec run, creates README.md.

    The stub writes the prompt it received (the last positional argument) and whether the OpenAI key
    was in its environment to a marker file, so a test can prove the task reached the CLI as the
    prompt and the key reached it only through the environment, never through the prompt text. It
    prints the JSONL event stream codex exec --json emits: an agent message and a token usage event.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "codex"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "if '--version' in args:\n"
        "    print('codex-cli 0.9.0 (stub)')\n"
        "    sys.exit(0)\n"
        "prompt = args[-1] if args else ''\n"
        "seen = {'prompt': prompt, 'key_in_env': os.environ.get('OPENAI_API_KEY', '')}\n"
        f"open({marker_path!r}, 'w').write(json.dumps(seen))\n"
        "with open('README.md', 'w') as fh:\n"
        "    fh.write('one line\\n')\n"
        "print(json.dumps({'type': 'thread.started', 'thread_id': 't_stub'}))\n"
        "print(json.dumps({\n"
        "    'type': 'item.completed',\n"
        "    'item': {'type': 'agent_message', 'text': 'Created README.md with one line.'},\n"
        "}))\n"
        "print(json.dumps({\n"
        "    'type': 'turn.completed',\n"
        "    'usage': {'input_tokens': 11, 'output_tokens': 7},\n"
        "}))\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script


@pytest.fixture()
def builds(tmp_path, monkeypatch):
    """Point the builds root at a throwaway directory and configure the OpenAI key."""
    monkeypatch.setattr(get_settings(), "nexa_runtime_root", str(tmp_path / "builds"))
    monkeypatch.setattr(get_settings(), "openai_api_key", _API_KEY)
    return tmp_path


@pytest.fixture()
def stub_on_path(tmp_path, monkeypatch):
    """Install the stub codex CLI and prepend it to PATH for the duration of the test."""
    marker = tmp_path / "cli_marker.json"
    _write_stub_codex(tmp_path / "bin", marker_path=str(marker))
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}")
    return marker


def _project(slug="readme-app-codex"):
    return Project(name="Readme App", slug=slug)


def test_registry_knows_codex_cli(builds):
    assert "codex-cli" in available_backends()
    backend = get_backend("codex-cli")
    assert isinstance(backend, CodexCliBackend)
    assert backend.name == "codex-cli"


def test_health_reports_available_when_cli_present_and_authed(builds, stub_on_path):
    health = CodexCliBackend().health()
    assert health.installed
    assert health.authed
    assert health.available
    assert "0.9.0" in health.detail


def test_health_reports_unavailable_when_cli_missing(builds):
    # A binary name that is not on PATH: not installed, so not available, with no exception.
    health = CodexCliBackend(cli="nexa-codex-not-installed").health()
    assert not health.installed
    assert not health.available
    assert "not found" in health.detail.lower()


def test_health_reports_unauthed_when_key_absent(stub_on_path, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_runtime_root", str(tmp_path / "builds"))
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    health = CodexCliBackend().health()
    assert health.installed
    assert not health.authed
    assert not health.available


def test_run_trivial_task_returns_a_diff_that_adds_the_file(builds, stub_on_path):
    ws = prepare_workspace(_project())
    result = CodexCliBackend().run(
        "Create README.md with one line.", ws, autonomy=1, timeout=60
    )

    assert isinstance(result, AgentResult)
    assert result.ok
    assert result.exit_code == 0
    assert not result.timed_out
    assert result.backend == "codex-cli"

    # The diff adds README.md with the one line.
    assert "README.md" in result.diff
    assert "+one line" in result.diff
    assert "README.md" in result.files_changed

    # The reasoning and the token estimate were parsed out of the CLI json event stream.
    assert "README.md" in result.reasoning
    assert result.cost_usd is None
    assert result.input_tokens == 11
    assert result.output_tokens == 7


def test_run_writes_only_inside_the_workspace(builds, stub_on_path):
    from app.engine import builds_root

    ws = prepare_workspace(_project(slug="confined-app-codex"))
    before = {p.name for p in builds_root().iterdir()}

    CodexCliBackend().run("Create README.md with one line.", ws, autonomy=1, timeout=60)

    # The file landed inside the workspace.
    assert (ws.path / "README.md").read_text(encoding="utf-8") == "one line\n"
    # Nothing new appeared at the builds root beside the workspace: the edit stayed in its box.
    after = {p.name for p in builds_root().iterdir()}
    assert after == before
    assert before == {"confined-app-codex"}


def test_provider_key_never_enters_the_prompt_or_the_result(builds, stub_on_path):
    ws = prepare_workspace(_project(slug="secret-app-codex"))
    result = CodexCliBackend().run(
        "Create README.md with one line.", ws, context="Project requirements here.", timeout=60
    )

    # The key never appears in anything returned to a caller.
    assert _API_KEY not in result.diff
    assert _API_KEY not in result.transcript
    assert _API_KEY not in result.reasoning

    # The CLI received the task as its prompt, with no key in the prompt text, and the key only
    # through its environment.
    marker = json.loads(stub_on_path.read_text(encoding="utf-8"))
    assert "Create README.md with one line." in marker["prompt"]
    assert _API_KEY not in marker["prompt"]
    assert marker["key_in_env"] == _API_KEY


def test_run_refuses_a_workspace_outside_the_builds_root(builds, stub_on_path, tmp_path):
    ws = prepare_workspace(_project(slug="ok-app-codex"))
    # Point the resolved path outside the builds root: the run must refuse before the CLI starts.
    ws.path = tmp_path / "elsewhere"
    (tmp_path / "elsewhere").mkdir()
    with pytest.raises(BackendError):
        CodexCliBackend().run("Create README.md with one line.", ws, timeout=60)
