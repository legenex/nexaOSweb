"""litellm based multi provider model router.

A YAML file maps semantic keys to concrete models and default sampling. Business logic
calls model_for(key) or route_completion(key, messages); it never names a model id.
litellm reads the provider keys from the environment, so secrets stay server side.

The same YAML also records the agents (research, build, dreaming, triage, journal) and
the semantic key each runs through, so the Settings UI can show and edit the mapping
without hardcoding a model id in the frontend. The registry helpers here load the full
config, add a per key cost hint, and write remaps back to disk additively.
"""

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# Resolved fresh on each read so tests can redirect it to a temporary file.
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "models.yaml"

# Sampling parameters that may be forwarded to the provider.
_ALLOWED_SAMPLING = {"temperature", "top_p", "max_tokens", "stop"}

# Header written above the regenerated YAML so the file stays self documenting.
_CONFIG_HEADER = (
    "# Semantic model keys mapped to concrete provider models.\n"
    "#\n"
    "# Business logic references the keys only, never a concrete model id. Swapping a model\n"
    "# is a one line change here (or through Settings, Models and Agents). litellm resolves\n"
    "# the provider prefixed id and reads the matching provider key from the environment.\n"
    "#\n"
    "# The agents block records which semantic key each agent runs through.\n"
)

# Rough blended price hint in USD per million tokens, matched by substring on the model id.
# A hint only, ordered most specific first; the provider invoice is the real number.
_COST_TABLE: list[tuple[str, str, float]] = [
    ("gpt-4o-mini", "low", 0.4),
    ("opus", "high", 30.0),
    ("sonnet", "medium", 9.0),
    ("haiku", "low", 2.0),
    ("gpt-4o", "medium", 7.5),
    ("gemini-1.5-pro", "medium", 5.0),
    ("gemini", "low", 1.0),
    ("mini", "low", 0.5),
]

_TIER_LABEL = {"low": "$", "medium": "$$", "high": "$$$", "unknown": "?"}

# Lazily bound litellm.completion so importing this module stays cheap and tests can
# inject a fake without importing litellm.
_completion_fn: Callable[..., Any] | None = None


def _get_completion() -> Callable[..., Any]:
    global _completion_fn
    if _completion_fn is None:
        import litellm

        _completion_fn = litellm.completion
    return _completion_fn


def normalize_sampling(entry: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {k: v for k, v in entry.items() if k in _ALLOWED_SAMPLING}
    params.update({k: v for k, v in overrides.items() if k in _ALLOWED_SAMPLING})
    if "temperature" in params:
        params["temperature"] = max(0.0, min(2.0, float(params["temperature"])))
    if "top_p" in params:
        params["top_p"] = max(0.0, min(1.0, float(params["top_p"])))
    if "max_tokens" in params:
        params["max_tokens"] = max(1, int(params["max_tokens"]))
    return params


def cost_hint(model_id: str) -> dict[str, Any]:
    """A coarse cost tier badge for a concrete model id. Display hint only."""
    name = model_id.lower()
    for needle, tier, price in _COST_TABLE:
        if needle in name:
            return {"tier": tier, "label": _TIER_LABEL[tier], "blended_per_mtok": price}
    return {"tier": "unknown", "label": _TIER_LABEL["unknown"], "blended_per_mtok": None}


class ModelRouter:
    def __init__(self, models: dict[str, dict[str, Any]]) -> None:
        self._models = models

    @property
    def keys(self) -> list[str]:
        return list(self._models.keys())

    def _entry(self, key: str) -> dict[str, Any]:
        if key not in self._models:
            raise KeyError(f"unknown model key: {key}")
        return self._models[key]

    def model_for(self, key: str) -> str:
        return str(self._entry(key)["model"])

    def params_for(self, key: str, **overrides: Any) -> dict[str, Any]:
        return normalize_sampling(self._entry(key), overrides)

    def route_completion(
        self, key: str, messages: list[dict[str, Any]], **overrides: Any
    ) -> Any:
        entry = self._entry(key)
        params = normalize_sampling(entry, overrides)
        completion = _get_completion()
        return completion(model=entry["model"], messages=messages, **params)


def load_config() -> dict[str, Any]:
    """The full models.yaml document, with models and agents blocks guaranteed present."""
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    data.setdefault("models", {})
    data.setdefault("agents", {})
    return data


def _load_models() -> dict[str, dict[str, Any]]:
    models = load_config().get("models", {})
    if not models:
        raise ValueError(f"no models configured in {CONFIG_PATH}")
    return models


def save_config(config: dict[str, Any]) -> None:
    """Write the full config back, additively. Refreshes the cached router."""
    body = yaml.safe_dump(
        {"models": config.get("models", {}), "agents": config.get("agents", {})},
        sort_keys=False,
        default_flow_style=False,
    )
    CONFIG_PATH.write_text(_CONFIG_HEADER + "\n" + body, encoding="utf-8")
    get_router.cache_clear()


@lru_cache
def get_router() -> ModelRouter:
    return ModelRouter(_load_models())
