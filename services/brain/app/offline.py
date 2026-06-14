"""Offline synthesis fallback.

When no model provider key is configured, or a provider call fails, the Brain still needs
to return structured output so the whole Flow pipeline is demonstrable. This module builds
a deterministic, schema shaped object from the prompt. It is not a model: it produces
sensible placeholder content so Classify, Process, and Clarify all function without keys.
Set a provider key to replace this with real generation.
"""

import re
from typing import Any

from app.router import model_router


def has_provider_keys() -> bool:
    """Whether any model provider key is available, connected through the store or the environment.

    Store first means a provider connected through the API counts here too, so the pipeline runs on
    that key with nothing in .env rather than falling back to offline synthesis.
    """
    return any(model_router.has_provider_key(p) for p in model_router.KNOWN_PROVIDERS)


def _subject(prompt: str) -> str:
    match = re.search(r"Name:\s*(.+)", prompt)
    if match:
        return match.group(1).strip().splitlines()[0][:80]
    return "the captured idea"


def _notes(prompt: str) -> str:
    match = re.search(r"(?:Body|Notes|Description):\s*(.+)", prompt)
    if match:
        return match.group(1).strip().splitlines()[0]
    return ""


# Sensible defaults for the keys the pipeline schemas use.
def _value_for(key: str, spec: dict[str, Any], prompt: str) -> Any:
    subject = _subject(prompt)
    notes = _notes(prompt)
    enum = spec.get("enum")
    kind = spec.get("type")

    if enum:
        # Prefer "project" for shape style enums so the full flow is exercised.
        return "project" if "project" in enum else enum[0]

    special: dict[str, Any] = {
        "confidence": 0.82,
        "reasoning_summary": (
            f"Offline mode classified {subject} as a project based on its scope and the "
            "presence of multiple deliverables."
        ),
        "tags": ["offline", "demo", "project"],
        "expanded": (
            f"{subject}. {notes} ".strip()
            + " A focused build with a clear objective, a small set of deliverables, and a "
            "concrete launch target for the US market."
        ),
        "summary": f"A structured plan to deliver {subject}.",
        "objective": f"Ship {subject} with a clear, testable outcome.",
        "recommended_outcome": f"A working version of {subject} in production.",
        "estimated_complexity": "medium",
        "proposed_build_destination": "local directory",
        "questions": [
            f"What is the target launch date for {subject}?",
            "Which integrations are required at launch?",
        ],
    }
    if key in special:
        return special[key]

    if kind == "array":
        return _array_for(key, subject)
    if kind == "number" or kind == "integer":
        return 1
    # default string
    return f"Offline {key.replace('_', ' ')} for {subject}."


def _array_for(key: str, subject: str) -> list[str]:
    presets: dict[str, list[str]] = {
        "project_tree": ["index.html", "styles.css", "app.ts", "README.md"],
        "workstreams": ["design", "build", "tracking", "launch"],
        "deliverables": [f"{subject} v1", "launch checklist"],
        "subtasks": ["scaffold the project", "wire the core flow", "add tracking"],
        "dependencies": ["brand assets", "domain", "analytics property"],
        "assets": ["logo", "copy doc", "reference screenshots"],
        "owners": ["Nick"],
        "open_questions": ["What is the primary success metric?"],
        "risks": ["scope creep", "unclear ownership"],
        "recommended_next_steps": ["clarify integrations", "approve at the gate"],
        "likely_integrations": ["github", "clickup", "google drive"],
    }
    return presets.get(key, [f"{subject} item one", f"{subject} item two"])


def offline_synthesize(prompt: str, schema: dict[str, Any] | None) -> dict[str, Any]:
    properties = (schema or {}).get("properties", {})
    if not properties:
        return {"text": f"Offline synthesis for {_subject(prompt)}."}
    return {key: _value_for(key, spec, prompt) for key, spec in properties.items()}
