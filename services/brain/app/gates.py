"""Smart approval gates and deny-by-default autonomy.

Two decisions live here, both deny-by-default.

can_auto_resolve: may a proposed step skip the human gate? Only at a higher autonomy level
(above 0) AND only when the step is explicitly classified low-risk AND reversible AND local AND
non-external, with no destructive, external, irreversible, credential, production, deploy, or
user-facing effect. An unclassified step, a missing or non-true safe tag, or any unsafe tag set
true means the step is gated. Unknown is treated as unsafe.

recommend_gate: the recommended_default and the proceed-or-change framing every approval request
carries, so a human sees a clear default and whether the decision materially affects the outcome.
proceed-and-flag is the philosophy: proceed on safe defaults, stop only when a decision
materially affects the outcome.

A step declares its classification in payload["risk"], a flat dict of booleans.
"""

from typing import Any

from app.models.runtime import AgentStep

# Every one of these must be explicitly True for a step to count as safe.
SAFE_TAGS = ("low_risk", "reversible", "local", "non_external")

# Any one of these set True keeps the human gate, regardless of the safe tags.
UNSAFE_TAGS = (
    "destructive",
    "external",
    "irreversible",
    "credential",
    "production",
    "deploy",
    "user_facing",
)


def _risk(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    risk = payload.get("risk")
    return risk if isinstance(risk, dict) and risk else None


def is_safe_set(payload: dict[str, Any] | None) -> bool:
    """True only if the step is fully classified safe.

    Deny-by-default: an unclassified step, any safe tag that is missing or not exactly True, or
    any unsafe tag set True, returns False. Unknown is treated as unsafe.
    """
    risk = _risk(payload)
    if risk is None:
        return False
    if not all(risk.get(tag) is True for tag in SAFE_TAGS):
        return False
    if any(risk.get(tag) is True for tag in UNSAFE_TAGS):
        return False
    return True


def materially_affects_outcome(payload: dict[str, Any] | None) -> bool:
    """A step materially affects the outcome when it is not in the safe set."""
    return not is_safe_set(payload)


def can_auto_resolve(payload: dict[str, Any] | None, autonomy_level: int) -> bool:
    """May this step skip the human gate? Deny-by-default; autonomy 0 never auto-resolves."""
    if autonomy_level <= 0:
        return False
    return is_safe_set(payload)


def recommend_for_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """The recommended default and proceed-or-change framing for a step payload.

    Pure over the payload, so a caller can compute the recommendation before a step exists and
    fold it into the payload it is about to author, rather than mutating an authored payload.
    """
    if materially_affects_outcome(payload):
        return {
            "recommended_default": "change",
            "materially_affects": True,
            "framing": (
                "This decision materially affects the outcome. Review and change it if needed "
                "before proceeding."
            ),
        }
    return {
        "recommended_default": "proceed",
        "materially_affects": False,
        "framing": "Safe default. Proceed unless you want to change it.",
    }


def recommend_gate(step: AgentStep) -> dict[str, Any]:
    """The recommended default and proceed-or-change framing for an approval request."""
    return recommend_for_payload(step.payload)
