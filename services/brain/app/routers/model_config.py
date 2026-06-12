"""Models and Agents settings.

A read and edit surface over config/models.yaml and the router. List every semantic key
with its mapped model and a cost hint, list the agents and the key each uses, remap a key
to a different provider model, and add a new key. Writes go back to the YAML through the
router's save_config, which refreshes the cached router so a remap takes effect at once.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status

from app.models.user import User
from app.router import model_router
from app.schemas.model_config import (
    AddModelRequest,
    AgentBinding,
    CostHint,
    ModelEntry,
    ModelsConfig,
    RemapKeyRequest,
)
from app.security.auth import current_user

router = APIRouter(prefix="/settings/models", tags=["settings", "models"])


def _entry_for(key: str, spec: dict) -> ModelEntry:
    model_id = str(spec.get("model", ""))
    return ModelEntry(
        key=key,
        model=model_id,
        temperature=spec.get("temperature"),
        max_tokens=spec.get("max_tokens"),
        cost=CostHint(**model_router.cost_hint(model_id)),
    )


def _config_view(config: dict) -> ModelsConfig:
    models: dict = config.get("models", {})
    agents: dict = config.get("agents", {})
    keys = [_entry_for(key, spec) for key, spec in models.items()]
    bindings = []
    for agent_id, spec in agents.items():
        model_key = str(spec.get("model_key", ""))
        resolved = models.get(model_key, {}).get("model") if model_key in models else None
        bindings.append(
            AgentBinding(
                id=agent_id,
                label=str(spec.get("label", agent_id)),
                description=str(spec.get("description", "")),
                model_key=model_key,
                resolved_model=resolved,
            )
        )
    return ModelsConfig(keys=keys, agents=bindings)


def _apply_sampling(spec: dict, temperature: float | None, max_tokens: int | None) -> None:
    if temperature is not None:
        spec["temperature"] = max(0.0, min(2.0, float(temperature)))
    if max_tokens is not None:
        spec["max_tokens"] = max(1, int(max_tokens))


@router.get("", response_model=ModelsConfig)
def get_models(user: User = Depends(current_user)) -> ModelsConfig:
    return _config_view(model_router.load_config())


@router.patch("/keys/{key}", response_model=ModelEntry)
def remap_key(
    key: str,
    payload: RemapKeyRequest,
    user: User = Depends(current_user),
) -> ModelEntry:
    config = model_router.load_config()
    models = config["models"]
    if key not in models:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"unknown model key: {key}")
    spec = dict(models[key])
    spec["model"] = payload.model
    _apply_sampling(spec, payload.temperature, payload.max_tokens)
    models[key] = spec
    model_router.save_config(config)
    return _entry_for(key, spec)


@router.post("/keys", response_model=ModelEntry, status_code=http_status.HTTP_201_CREATED)
def add_key(
    payload: AddModelRequest,
    user: User = Depends(current_user),
) -> ModelEntry:
    config = model_router.load_config()
    models = config["models"]
    if payload.key in models:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT, f"model key already exists: {payload.key}"
        )
    spec: dict = {"model": payload.model}
    _apply_sampling(spec, payload.temperature, payload.max_tokens)
    models[payload.key] = spec
    model_router.save_config(config)
    return _entry_for(payload.key, spec)
