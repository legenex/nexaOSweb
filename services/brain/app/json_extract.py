"""Structured JSON generation.

synthesize_json(key, prompt, schema) asks the model named by the semantic key for a
single JSON object, then parses it. A forgiving parser tolerates a model that wraps the
object in prose or a code fence.
"""

import json
import logging
import re
from typing import Any

from app.offline import has_provider_keys, offline_synthesize
from app.router import model_router
from app.router.model_router import ModelRouter, get_router

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _extract_content(response: Any) -> str:
    """Read the assistant text from a litellm style response or a plain dict."""
    try:
        return response.choices[0].message.content  # litellm object
    except AttributeError:
        pass
    try:
        return response["choices"][0]["message"]["content"]  # dict shape
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("could not read content from completion response") from exc


def parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    # Strip a leading code fence if present.
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1 :] if "\n" in text else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(content)
        if match is None:
            raise ValueError("no JSON object found in model output") from None
        return json.loads(match.group(0))


def synthesize_json(
    key: str,
    prompt: str,
    schema: dict[str, Any] | None = None,
    *,
    router: ModelRouter | None = None,
) -> dict[str, Any]:
    router = router or get_router()
    system = (
        "You are a structured data generator. Respond with a single valid JSON object "
        "and nothing else. Do not include commentary or a code fence."
    )
    if schema is not None:
        system += f" The JSON must conform to this JSON schema: {json.dumps(schema)}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    # With no provider key and no injected completion (tests), use the offline fallback
    # rather than calling a provider that would fail.
    if not has_provider_keys() and model_router._completion_fn is None:
        return offline_synthesize(prompt, schema)

    try:
        response = router.route_completion(key, messages)
        return parse_json(_extract_content(response))
    except Exception:  # noqa: BLE001  fall back so the pipeline still produces output
        logger.warning("provider synthesis failed for key %s, using offline fallback", key)
        return offline_synthesize(prompt, schema)
