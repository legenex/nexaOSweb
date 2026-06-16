"""Autonomy levels and deterministic risk gating. The agent proposes; this layer disposes.

Every task carries an autonomy level, a dial with three settings:

  - green: the run goes start to finish unattended. The build run auto resolves its own Human Gate
    and merges without a person in the loop.
  - yellow: the run pauses at the Human Gate and waits for a person to approve before anything leaves
    the isolated worktree.
  - red: the run never auto runs. It always stops for an explicit human decision, and the specific
    destructive or irreversible action is refused outright at the command layer.

On top of the dial sits a deterministic classifier, not a learned model and not the agent's own
judgement. Given the task text, the files a run touched, and any commands, it marks anything that
touches auth, payments or money, database migrations, deploy or infra, or secrets as at least yellow,
and the destructive or irreversible actions (file deletion, a git force push, a push to a protected
branch, dropping or truncating data, a hard reset or history rewrite) as red, regardless of the
level the task was set to. The classifier can only escalate the risk (lower the autonomy), never relax
it: a green task that edits an auth file is forced to the gate; a force push is forced to red.

This module is pure and deterministic: the same inputs always yield the same level, with the matched
categories and human readable reasons recorded so a person can see exactly why a run was gated.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.safety import PROTECTED_BRANCHES

# The three dial settings, ordered from most to least autonomous. A higher rank is more restrictive
# (more risk, less autonomy), so escalation always takes the maximum rank.
GREEN = "green"
YELLOW = "yellow"
RED = "red"
LEVELS: tuple[str, ...] = (GREEN, YELLOW, RED)
_RANK = {GREEN: 0, YELLOW: 1, RED: 2}

# The safe deny-by-default level when none is set: pause at the gate rather than run unattended.
DEFAULT_LEVEL = YELLOW


def normalize_level(value: str | None, default: str = DEFAULT_LEVEL) -> str:
    """Coerce a level string to one of the three settings, falling back to a default when unknown."""
    candidate = (value or "").strip().lower()
    return candidate if candidate in _RANK else default


def is_valid_level(value: str | None) -> bool:
    """Whether a string is exactly one of the three dial settings."""
    return (value or "").strip().lower() in _RANK


def escalate(*levels: str | None) -> str:
    """The most restrictive of the given levels: risk only ever rises, never falls.

    Used to fold the task's set level together with the classifier's verdict, so a green task whose
    change trips a yellow or red rule is gated, but a rule can never make a red task greener.
    """
    best = GREEN
    for level in levels:
        normalized = normalize_level(level, GREEN)
        if _RANK[normalized] > _RANK[best]:
            best = normalized
    return best


# --- the deterministic risk classifier ----------------------------------------------------

# A rule is a category label and a compiled pattern. Yellow rules force at least the gate; red rules
# force red regardless of the task's set level. Patterns are matched case insensitively against the
# task text, the touched file paths, the commands, and the diff. Word boundaries keep them from
# firing on substrings of unrelated identifiers.
_PROTECTED_ALT = "|".join(re.escape(b) for b in PROTECTED_BRANCHES)

_RED_RULES: list[tuple[str, re.Pattern[str]]] = [
    # A git force push, the irreversible overwrite of a remote branch.
    ("force_push", re.compile(r"git\s+push\b[^\n]*?(--force\b|--force-with-lease\b|(?<!\S)-f\b)")),
    # A push to a protected branch, even without a force flag.
    ("protected_branch", re.compile(rf"git\s+push\b[^\n]*?\b({_PROTECTED_ALT})\b")),
    # Deleting a remote branch by pushing an empty ref.
    ("protected_branch", re.compile(rf"git\s+push\b[^\n]*?:\s*(refs/heads/)?({_PROTECTED_ALT})\b")),
    # File deletion at the shell.
    ("file_deletion", re.compile(r"\brm\s+-[a-z]*[rf]")),
    ("file_deletion", re.compile(r"\b(git\s+rm|rmdir|unlink|shred)\b")),
    # File deletion as it appears in a unified diff.
    ("file_deletion", re.compile(r"(?m)^deleted file mode\b")),
    # Irreversible data loss in SQL.
    ("data_loss", re.compile(r"\b(drop\s+(table|database|schema)|truncate\s+table?|delete\s+from)\b")),
    # History rewrites and hard resets, which discard committed work.
    ("history_rewrite", re.compile(r"git\s+(reset\s+--hard|filter-branch|filter-repo)\b")),
]

_YELLOW_RULES: list[tuple[str, re.Pattern[str]]] = [
    # Authentication, authorization, sessions, and access control.
    (
        "auth",
        re.compile(
            r"\b(auth|authn|authz|oauth|openid|login|logout|signin|sign-in|session|jwt|"
            r"password|passwd|credential|permission|rbac|authorize|authentication|middleware)\b"
        ),
    ),
    # Payments and money.
    (
        "payments",
        re.compile(
            r"\b(payment|stripe|paypal|billing|invoice|checkout|charge|payout|refund|"
            r"subscription|money|currency|price|pricing|wallet|ledger)\b"
        ),
    ),
    # Database migrations and schema changes.
    (
        "db_migration",
        re.compile(
            r"\b(migration|migrations|alembic|migrate|schema|alter\s+table|create\s+table|"
            r"add_column|drop_column|create_index)\b"
        ),
    ),
    # Deploy and infrastructure.
    (
        "deploy_infra",
        re.compile(
            r"\b(deploy|deployment|dockerfile|docker-compose|kubernetes|k8s|terraform|ansible|"
            r"nginx|systemd|helm|infra|infrastructure|pipeline|cicd|ci/cd)\b|\.github/workflows"
        ),
    ),
    # Secrets and credentials material.
    (
        "secrets",
        re.compile(
            r"\b(secret|secrets|api[_-]?key|apikey|access[_-]?key|private[_-]?key|token|"
            r"credentials|id_rsa)\b|\.env\b|-----BEGIN"
        ),
    ),
]


@dataclass
class RiskAssessment:
    """The verdict of the classifier: a level, the categories that fired, and human readable reasons.

    level is one of green, yellow, red. categories lists the distinct risk categories matched (for
    example auth, force_push). reasons pairs each match with where it was seen, so a person reviewing
    a gated run sees exactly why. A green assessment has no categories and no reasons.
    """

    level: str = GREEN
    categories: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def forces_gate(self) -> bool:
        """True when the assessment is at least yellow, so the run must stop at the Human Gate."""
        return _RANK[self.level] >= _RANK[YELLOW]

    @property
    def is_red(self) -> bool:
        """True when a destructive or irreversible action was detected."""
        return self.level == RED


def _scan(label: str, content: str, rules: list[tuple[str, re.Pattern[str]]]) -> list[tuple[str, str]]:
    """Match a body of text against a rule set, returning (category, reason) for each hit."""
    hits: list[tuple[str, str]] = []
    text = content or ""
    if not text.strip():
        return hits
    lowered = text.lower()
    for category, pattern in rules:
        match = pattern.search(lowered)
        if match:
            snippet = match.group(0).strip()[:60]
            hits.append((category, f"{category}: matched '{snippet}' in {label}"))
    return hits


def classify_risk(
    *,
    text: str = "",
    files: Sequence[str] = (),
    commands: Sequence[str] = (),
    diff: str = "",
) -> RiskAssessment:
    """Classify the risk of a change deterministically into green, yellow, or red.

    text is the task's words (title, detail, goal). files are the paths a run touched. commands are
    any shell commands it would run. diff is the unified diff of the proposed change. Red rules win
    over yellow rules; any red hit makes the whole assessment red. The result records every category
    that fired and a reason for each, so the gate decision is fully explainable.
    """
    bodies: list[tuple[str, str]] = [
        ("task", text or ""),
        ("files", "\n".join(files)),
        ("commands", "\n".join(commands)),
        ("diff", diff or ""),
    ]

    red_hits: list[tuple[str, str]] = []
    yellow_hits: list[tuple[str, str]] = []
    for label, body in bodies:
        red_hits.extend(_scan(label, body, _RED_RULES))
        yellow_hits.extend(_scan(label, body, _YELLOW_RULES))

    if red_hits:
        return _assemble(RED, red_hits + yellow_hits)
    if yellow_hits:
        return _assemble(YELLOW, yellow_hits)
    return RiskAssessment(level=GREEN)


def _assemble(level: str, hits: Iterable[tuple[str, str]]) -> RiskAssessment:
    """Build an assessment from raw hits, de duplicating categories and reasons while keeping order."""
    categories: list[str] = []
    reasons: list[str] = []
    for category, reason in hits:
        if category not in categories:
            categories.append(category)
        if reason not in reasons:
            reasons.append(reason)
    return RiskAssessment(level=level, categories=categories, reasons=reasons)


def gate_decision(task_level: str | None, assessment: RiskAssessment) -> dict:
    """Fold the task's set level with the classifier verdict into the effective gate decision.

    Returns the effective level (the more restrictive of the two), whether the run may auto advance
    (only a fully green outcome does), and the categories and reasons behind any escalation. This is
    the single place the build engine consults to decide green-go, yellow-gate, or red-stop.
    """
    set_level = normalize_level(task_level)
    effective = escalate(set_level, assessment.level)
    return {
        "task_level": set_level,
        "classifier_level": assessment.level,
        "effective_level": effective,
        "auto_advance": effective == GREEN,
        "is_red": effective == RED,
        "categories": list(assessment.categories),
        "reasons": list(assessment.reasons),
    }
