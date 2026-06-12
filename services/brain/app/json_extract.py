"""Structured JSON generation.

synthesize_json(key, prompt, schema) asks the model named by the semantic key for a
single JSON object, then parses it. A forgiving parser tolerates a model that wraps the
object in prose or a code fence.
"""

import json
import re
from typing import Any

from app.router.model_router import ModelRouter, get_router

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
            raise ValueError("no JSON object found in model output")
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
    response = router.route_completion(key, messages)
    return parse_json(_extract_content(response))
