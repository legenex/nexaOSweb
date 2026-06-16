"""The autonomy dial and the deterministic risk classifier.

These tests prove the pure classification layer without a database or an agent: the level helpers, the
escalation that only ever raises risk, the rules that force sensitive work to at least yellow and
destructive or irreversible actions to red, and the gate decision that folds a task's set level with
the classifier verdict. The classifier is deterministic, so the same inputs always yield the same
level with explainable reasons.
"""

from app.autonomy import (
    GREEN,
    RED,
    YELLOW,
    classify_risk,
    escalate,
    gate_decision,
    is_valid_level,
    normalize_level,
)

# --- level helpers ------------------------------------------------------------------------


def test_normalize_level_coerces_and_defaults():
    assert normalize_level("green") == GREEN
    assert normalize_level("YELLOW") == YELLOW
    assert normalize_level("  red ") == RED
    assert normalize_level("purple") == YELLOW  # unknown falls to the safe default
    assert normalize_level(None) == YELLOW
    assert normalize_level("nonsense", default=GREEN) == GREEN


def test_is_valid_level():
    assert is_valid_level("green") and is_valid_level("YELLOW") and is_valid_level("red")
    assert not is_valid_level("orange")
    assert not is_valid_level(None)


def test_escalate_only_raises_risk():
    assert escalate(GREEN, GREEN) == GREEN
    assert escalate(GREEN, YELLOW) == YELLOW
    assert escalate(YELLOW, GREEN) == YELLOW
    assert escalate(GREEN, RED) == RED
    assert escalate(RED, GREEN, YELLOW) == RED
    # An unknown level is treated as green for escalation, never silently restrictive on its own.
    assert escalate("unknown", GREEN) == GREEN


# --- green: nothing sensitive -------------------------------------------------------------


def test_benign_change_is_green():
    a = classify_risk(
        text="Create README.md with one line",
        files=["README.md", "docs/intro.txt"],
        diff="diff --git a/README.md b/README.md\n+one line\n",
    )
    assert a.level == GREEN
    assert a.categories == []
    assert not a.forces_gate
    assert not a.is_red


# --- yellow: sensitive, forced to at least the gate ---------------------------------------


def test_auth_file_forces_at_least_yellow():
    a = classify_risk(text="green", files=["app/security/auth.py"])
    assert a.level == YELLOW
    assert "auth" in a.categories
    assert a.forces_gate
    assert a.reasons  # a human readable reason is recorded


def test_payments_text_is_yellow():
    a = classify_risk(text="Add a Stripe checkout and a refund flow")
    assert a.level == YELLOW
    assert "payments" in a.categories


def test_database_migration_is_yellow():
    a = classify_risk(files=["services/brain/migrations/versions/0099_add_column.py"])
    assert a.level == YELLOW
    assert "db_migration" in a.categories


def test_deploy_infra_is_yellow():
    a = classify_risk(files=[".github/workflows/deploy.yml"])
    assert a.level == YELLOW
    assert "deploy_infra" in a.categories


def test_secrets_is_yellow():
    a = classify_risk(text="rotate the API_KEY", files=[".env"])
    assert a.level == YELLOW
    assert "secrets" in a.categories


# --- red: destructive or irreversible, regardless of set level ----------------------------


def test_force_push_is_red():
    a = classify_risk(commands=["git push --force origin feature"])
    assert a.level == RED
    assert "force_push" in a.categories
    assert a.is_red


def test_force_with_lease_is_red():
    a = classify_risk(commands=["git push --force-with-lease origin feature"])
    assert a.level == RED
    assert "force_push" in a.categories


def test_push_to_protected_branch_is_red():
    a = classify_risk(commands=["git push origin main"])
    assert a.level == RED
    assert "protected_branch" in a.categories


def test_file_deletion_command_is_red():
    a = classify_risk(commands=["rm -rf build/"])
    assert a.level == RED
    assert "file_deletion" in a.categories


def test_file_deletion_in_diff_is_red():
    a = classify_risk(diff="deleted file mode 100644\n--- a/old.py\n+++ /dev/null\n")
    assert a.level == RED
    assert "file_deletion" in a.categories


def test_data_loss_sql_is_red():
    assert classify_risk(text="DROP TABLE users").level == RED
    assert classify_risk(text="truncate table sessions").level == RED


def test_history_rewrite_is_red():
    a = classify_risk(commands=["git reset --hard HEAD~3"])
    assert a.level == RED
    assert "history_rewrite" in a.categories


def test_red_wins_over_yellow_in_the_same_change():
    a = classify_risk(text="update auth", commands=["git push --force origin main"])
    assert a.level == RED
    # The yellow category is still recorded alongside the red ones for a full picture.
    assert "force_push" in a.categories
    assert "auth" in a.categories


# --- the gate decision: fold the set level with the classifier ----------------------------


def test_green_task_with_benign_change_auto_advances():
    decision = gate_decision("green", classify_risk(text="add a heading", files=["README.md"]))
    assert decision["effective_level"] == GREEN
    assert decision["auto_advance"] is True
    assert decision["is_red"] is False


def test_green_task_touching_auth_is_forced_to_the_gate():
    decision = gate_decision("green", classify_risk(files=["src/auth/login.py"]))
    assert decision["effective_level"] == YELLOW
    assert decision["auto_advance"] is False
    assert "auth" in decision["categories"]


def test_green_task_with_force_push_is_forced_red():
    decision = gate_decision("green", classify_risk(commands=["git push -f origin main"]))
    assert decision["effective_level"] == RED
    assert decision["is_red"] is True
    assert decision["auto_advance"] is False


def test_yellow_task_never_auto_advances_even_when_change_is_benign():
    decision = gate_decision("yellow", classify_risk(text="add a heading"))
    assert decision["effective_level"] == YELLOW
    assert decision["auto_advance"] is False


def test_red_task_stays_red_even_when_change_is_benign():
    decision = gate_decision("red", classify_risk(text="add a heading"))
    assert decision["effective_level"] == RED
    assert decision["auto_advance"] is False
