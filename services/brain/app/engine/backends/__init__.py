"""Agent backends: the external coding CLIs the engine drives, behind one AgentBackend interface.

A backend is selected by its config key, never by a hardcoded branch in business logic, in the same
spirit as the model router. Claude Code is the default; Codex CLI is always wired; Grok Build is wired
only when its feature flag (NEXA_ENABLE_GROK) is on. get_backend resolves a key to a ready instance
and available_backends lists the keys the engine may select right now.

The selectable set is computed fresh on each call from the feature flags, so a flag flip (or a test
monkeypatch of settings) takes effect immediately: while Grok is off it is absent from
available_backends and get_backend("grok-build") is refused, so nothing depends on Grok. Its health
can still be probed directly through GrokBuildBackend().health(), which reports the backend disabled.
"""

from collections.abc import Callable

from app.engine.backends.base import (
    AgentBackend,
    AgentResult,
    BackendError,
    BackendHealth,
)
from app.engine.backends.claude_code import (
    DEFAULT_AGENT_TIMEOUT_SECONDS,
    ClaudeCodeBackend,
)
from app.engine.backends.codex_cli import (
    CodexCliBackend,
)
from app.engine.backends.grok_build import (
    GrokBuildBackend,
    _grok_enabled,
)

# The default backend key. The engine resolves this when no backend is named, the way the model
# router resolves a semantic key, so swapping the default is a config change, not a code change.
DEFAULT_BACKEND = "claude-code"

# Always selectable backends: config key to backend class. Claude Code and Codex need no flag.
_ALWAYS_ON: dict[str, type[AgentBackend]] = {
    ClaudeCodeBackend.name: ClaudeCodeBackend,
    CodexCliBackend.name: CodexCliBackend,
}

# Feature flagged backends: config key to (backend class, a predicate that is true when its flag is
# on). A flagged backend joins the selectable set only while its predicate holds. Grok Build is the
# only one today; a new flagged backend is one more entry here, never a branch at the call sites.
_FLAGGED: dict[str, tuple[type[AgentBackend], Callable[[], bool]]] = {
    GrokBuildBackend.name: (GrokBuildBackend, _grok_enabled),
}


def _active_registry() -> dict[str, type[AgentBackend]]:
    """The backends selectable right now: the always on set plus any flagged backend whose flag is
    on. Recomputed per call so a flag flip takes effect immediately."""
    registry: dict[str, type[AgentBackend]] = dict(_ALWAYS_ON)
    for key, (backend_cls, enabled) in _FLAGGED.items():
        if enabled():
            registry[key] = backend_cls
    return registry


def available_backends() -> list[str]:
    """The backend keys the engine may select right now, for config validation and a settings
    surface. A flagged backend whose flag is off is absent."""
    return sorted(_active_registry())


def get_backend(name: str | None = None) -> AgentBackend:
    """Resolve a selectable backend key to a ready instance. Defaults to the configured default
    backend. A flagged backend whose flag is off is not selectable and is refused like an unknown
    key, so a disabled backend can never be dispatched to."""
    key = (name or DEFAULT_BACKEND).strip()
    backend_cls = _active_registry().get(key)
    if backend_cls is None:
        known = ", ".join(available_backends())
        raise BackendError(f"unknown agent backend '{key}'. known backends: {known}")
    return backend_cls()


# Imported last so the selector's lazy imports of available_backends/get_backend resolve cleanly.
from app.engine.backends.selector import (  # noqa: E402
    BackendChoice,
    load_policy,
    select_backend,
)

__all__ = [
    "AgentBackend",
    "AgentResult",
    "BackendError",
    "BackendHealth",
    "BackendChoice",
    "ClaudeCodeBackend",
    "CodexCliBackend",
    "GrokBuildBackend",
    "DEFAULT_AGENT_TIMEOUT_SECONDS",
    "DEFAULT_BACKEND",
    "available_backends",
    "get_backend",
    "load_policy",
    "select_backend",
]
