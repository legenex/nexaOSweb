"""litellm based multi provider model router.

A YAML file maps semantic keys to concrete models and default sampling. Business logic
calls model_for(key) or route_completion(key, messages); it never names a model id.
litellm reads the provider keys from the environment, so secrets stay server side.
"""

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "models.yaml"

# Sampling parameters that may be forwarded to the provider.
_ALLOWED_SAMPLING = {"temperature", "top_p", "max_tokens", "stop"}

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


def _load_models(path: Path = CONFIG_PATH) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    models = data.get("models", {})
    if not models:
        raise ValueError(f"no models configured in {path}")
    return models


@lru_cache
def get_router() -> ModelRouter:
    return ModelRouter(_load_models())
