"""The declarative agent backend selector.

A build run must choose which coding agent backend runs it. That choice is a policy, not a hardcoded
branch and not a learned model: config/agents.yaml maps a task type or a task's tags to a preferred
backend and an ordered fallback list, with a per backend cost ceiling, the same discipline models.yaml
holds for models. This module reads that policy and resolves a single backend for a run.

Resolution is deterministic:

  1. Build the ordered candidate list. A manual override (a backend named on the run) is tried first.
     Then the policy's order for the run: the first of the task's tags that the policy names wins,
     else the task type's entry, else the default entry, each yielding its preferred backend followed
     by its fallbacks.
  2. Walk the order and pick the first candidate that is selectable (registered and, for a feature
     flagged backend, enabled), reports available from its health probe (CLI installed and authed),
     and is not over its cost ceiling when an estimate is known. Skip the rest.

The chosen backend, the order considered, and why each candidate was skipped are returned in a
BackendChoice so the caller can record on the AgentRun which backend ran and why. Nothing here ever
runs an agent or makes a model call; it only consults the cheap health probes. The selector never
blocks on Grok: a disabled or unavailable backend is simply skipped to the next in the order.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.engine.backends.base import BackendHealth

# Resolved fresh on each read so a deployment edit (or a test) is picked up without reimporting.
# selector.py sits at app/engine/backends/, so the config dir is three parents up then config/.
CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "agents.yaml"


@dataclass
class _Candidate:
    """One backend considered during resolution, and the verdict on it."""

    backend: str
    selectable: bool
    available: bool
    over_ceiling: bool
    chosen: bool
    reason: str


@dataclass
class BackendChoice:
    """The outcome of resolving a backend for a run: which one to use and the trail of why.

    backend is the chosen backend key, or None when no candidate in the order was usable. preferred
    is the preferred backend the policy named (before fallbacks). policy_source records what produced
    the order ("override", "tag:<name>", "task_type:<type>", or "default"). order is the full ordered
    candidate list considered. considered carries the per candidate verdict for the ledger. reason is
    a short human summary. These are recorded on the AgentRun so the choice is auditable, never hidden.
    """

    backend: str | None
    preferred: str
    policy_source: str
    order: list[str] = field(default_factory=list)
    override: str | None = None
    considered: list[dict] = field(default_factory=list)
    reason: str = ""


def load_policy() -> dict[str, Any]:
    """The full agents.yaml document, with every block guaranteed present and shaped.

    Missing or malformed blocks fall back to safe defaults so a partial or absent config never breaks
    selection: the default policy alone still resolves a backend.
    """
    try:
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    default = data.get("default")
    if not isinstance(default, dict) or not default.get("preferred"):
        # Last resort only, when the config is absent or corrupt. The real default lives in the YAML.
        from app.engine.backends import DEFAULT_BACKEND

        default = {"preferred": DEFAULT_BACKEND, "fallbacks": []}
    data["default"] = _clean_entry(default)
    data["task_types"] = _clean_map(data.get("task_types"))
    data["tags"] = _clean_map(data.get("tags"))
    ceilings = data.get("cost_ceilings")
    data["cost_ceilings"] = ceilings if isinstance(ceilings, dict) else {}
    return data


def _clean_entry(entry: Any) -> dict[str, Any]:
    """Normalise one policy entry to {preferred: str, fallbacks: [str, ...]}."""
    if not isinstance(entry, dict):
        return {"preferred": "", "fallbacks": []}
    preferred = str(entry.get("preferred") or "").strip()
    raw = entry.get("fallbacks")
    fallbacks = [str(x).strip() for x in raw if str(x).strip()] if isinstance(raw, list) else []
    return {"preferred": preferred, "fallbacks": fallbacks}


def _clean_map(block: Any) -> dict[str, dict[str, Any]]:
    """Normalise a map of name to policy entry, dropping entries with no preferred backend."""
    out: dict[str, dict[str, Any]] = {}
    if isinstance(block, dict):
        for key, entry in block.items():
            cleaned = _clean_entry(entry)
            if cleaned["preferred"]:
                out[str(key)] = cleaned
    return out


def _order_from_entry(entry: dict[str, Any]) -> list[str]:
    """The ordered candidate list for a policy entry: preferred then fallbacks, de duplicated."""
    order: list[str] = []
    for name in [entry.get("preferred", "")] + list(entry.get("fallbacks", [])):
        name = str(name).strip()
        if name and name not in order:
            order.append(name)
    return order


def _resolve_policy(
    policy: dict[str, Any], task_type: str | None, tags: Sequence[str]
) -> tuple[dict[str, Any], str]:
    """Pick the policy entry for a run and the source label that explains the pick.

    A tag wins first: the first of the task's tags that the policy's tags block names. Then the task
    type's entry. Then the default. The source label is recorded on the choice for the ledger.
    """
    tag_block = policy.get("tags", {})
    for tag in tags:
        key = str(tag).strip()
        if key in tag_block:
            return tag_block[key], f"tag:{key}"
    type_block = policy.get("task_types", {})
    if task_type:
        key = str(task_type).strip()
        if key in type_block:
            return type_block[key], f"task_type:{key}"
    return policy["default"], "default"


def _default_available() -> list[str]:
    from app.engine.backends import available_backends

    return available_backends()


def _default_probe(name: str) -> BackendHealth:
    from app.engine.backends import get_backend

    return get_backend(name).health()


def select_backend(
    *,
    task_type: str | None = None,
    tags: Sequence[str] = (),
    override: str | None = None,
    cost_estimates: Mapping[str, float] | None = None,
    policy: dict[str, Any] | None = None,
    available: Callable[[], list[str]] | None = None,
    probe: Callable[[str], BackendHealth] | None = None,
) -> BackendChoice:
    """Resolve a single backend for a run from the declarative policy and the health probes.

    task_type and tags key into config/agents.yaml; override is a backend named manually on the run,
    tried first. cost_estimates maps a backend to its projected USD for this run; a candidate whose
    estimate exceeds its configured ceiling is skipped. available and probe are injectable so a test
    can resolve without real CLIs; they default to the live registry and health probes.

    Returns a BackendChoice: backend is the first candidate that is selectable, available, and within
    its ceiling, or None when the whole order is exhausted. The trail of candidates and the reason are
    always populated so the caller can record on the run which backend ran and why.
    """
    policy = policy or load_policy()
    available_fn = available or _default_available
    probe_fn = probe or _default_probe
    estimates = cost_estimates or {}
    ceilings = policy.get("cost_ceilings", {})

    entry, policy_source = _resolve_policy(policy, task_type, tags)
    preferred = entry["preferred"]
    order = _order_from_entry(entry)

    override_key = (override or "").strip()
    if override_key:
        order = [override_key] + [name for name in order if name != override_key]

    selectable_set = set(available_fn())
    considered: list[_Candidate] = []
    chosen: str | None = None
    chosen_source = policy_source

    for name in order:
        if name not in selectable_set:
            considered.append(
                _Candidate(name, False, False, False, False, "not selectable (unknown or disabled)")
            )
            continue
        health = probe_fn(name)
        if not health.available:
            detail = (health.detail or "unavailable").strip()
            considered.append(_Candidate(name, True, False, False, False, detail))
            continue
        ceiling = ceilings.get(name)
        estimate = estimates.get(name)
        if (
            isinstance(ceiling, (int, float))
            and isinstance(estimate, (int, float))
            and estimate > ceiling
        ):
            considered.append(
                _Candidate(
                    name,
                    True,
                    True,
                    True,
                    False,
                    f"estimated ${estimate:.4f} over ${float(ceiling):.4f} ceiling",
                )
            )
            continue
        considered.append(_Candidate(name, True, True, False, True, "chosen"))
        chosen = name
        if override_key and name == override_key:
            chosen_source = "override"
        break

    considered_dicts = [
        {
            "backend": c.backend,
            "selectable": c.selectable,
            "available": c.available,
            "over_ceiling": c.over_ceiling,
            "chosen": c.chosen,
            "reason": c.reason,
        }
        for c in considered
    ]
    if chosen is not None:
        reason = f"selected {chosen} ({chosen_source})"
    else:
        tried = ", ".join(order) if order else "none"
        reason = f"no backend available in order [{tried}]"

    return BackendChoice(
        backend=chosen,
        preferred=preferred,
        policy_source=chosen_source if chosen is not None else policy_source,
        order=order,
        override=override_key or None,
        considered=considered_dicts,
        reason=reason,
    )
