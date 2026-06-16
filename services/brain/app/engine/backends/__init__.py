"""Agent backends: the external coding CLIs the engine drives, behind one AgentBackend interface.

A backend is selected by its config key, never by a hardcoded branch in business logic, in the same
spirit as the model router. Claude Code is the default; Codex CLI is wired here too, and Grok Build is
recorded as a later addition. get_backend resolves a key to a ready instance and available_backends
lists the keys the engine knows.
"""

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

# The default backend key. The engine resolves this when no backend is named, the way the model
# router resolves a semantic key, so swapping the default is a config change, not a code change.
DEFAULT_BACKEND = "claude-code"

# Config key to backend class. Grok Build (feature flagged off) joins here later, each as one more
# entry, never a branch at the call sites that drive the AgentBackend interface.
_REGISTRY: dict[str, type[AgentBackend]] = {
    ClaudeCodeBackend.name: ClaudeCodeBackend,
    CodexCliBackend.name: CodexCliBackend,
}


def available_backends() -> list[str]:
    """The backend keys the engine knows, for config validation and a settings surface."""
    return sorted(_REGISTRY)


def get_backend(name: str | None = None) -> AgentBackend:
    """Resolve a backend key to a ready instance. Defaults to the configured default backend."""
    key = (name or DEFAULT_BACKEND).strip()
    backend_cls = _REGISTRY.get(key)
    if backend_cls is None:
        known = ", ".join(available_backends())
        raise BackendError(f"unknown agent backend '{key}'. known backends: {known}")
    return backend_cls()


__all__ = [
    "AgentBackend",
    "AgentResult",
    "BackendError",
    "BackendHealth",
    "ClaudeCodeBackend",
    "CodexCliBackend",
    "DEFAULT_AGENT_TIMEOUT_SECONDS",
    "DEFAULT_BACKEND",
    "available_backends",
    "get_backend",
]
