"""Readiness evaluation over the five knowledge sources."""

import json

from app.agents.context import inject_context
from app.agents.readiness import (
    KNOWN,
    NEEDS_CREDENTIAL,
    NEEDS_USER,
    READINESS_KIND,
    UNKNOWN,
    evaluate_readiness,
    readiness_assessment,
    readiness_satisfied,
    readiness_steps,
)
from app.models.knowledge import KnowledgeEntry
from app.models.project import Integration
from app.models.user import User
from app.runtime import (
    COMPLETED_UNVERIFIED,
    PLANNED,
    WAITING_APPROVAL,
    create_run,
    resolve_approval,
)


def _user(db):
    user = User(email="nick@example.com", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _know(db, content, scope="development"):
    db.add(
        KnowledgeEntry(
            kind="fact",
            scope=scope,
            source="manual",
            content=content,
            confidence=0.9,
            status="active",
            provenance={},
        )
    )
    db.commit()


def _by_key(db, run):
    return {
        (step.payload.get("readiness") or {}).get("key"): step
        for step in readiness_steps(db, run)
    }


def test_over_seeded_plan_resolves_from_sources_without_asking(db_session):
    user = _user(db_session)
    # A decision the knowledge base already answers, and an integration already connected.
    _know(db_session, "Hosting is Plesk on a Linux VPS with Nginx.")
    db_session.add(
        Integration(
            user_id=user.id,
            provider="stripe",
            status="connected",
            credentials_ref="vault://stripe",
        )
    )
    db_session.commit()

    plan = {
        "requirements": [
            {
                "key": "hosting",
                "question": "Where is the app hosted?",
                "kind": "decision",
                "keywords": ["hosting", "plesk"],
            },
            {
                "key": "credential:stripe",
                "question": "Connect Stripe.",
                "kind": "credential",
                "provider": "stripe",
            },
        ]
    }

    run = evaluate_readiness(db_session, plan=plan)
    assert run.kind == READINESS_KIND

    steps = _by_key(db_session, run)
    # Nothing is held at the gate: both items were answered from the sources.
    assert all(step.status != WAITING_APPROVAL for step in steps.values())

    hosting = steps["hosting"]
    assert hosting.status == COMPLETED_UNVERIFIED
    assert hosting.payload["readiness"]["resolution"] == KNOWN
    assert hosting.payload["readiness"]["source"] == "knowledge_base"
    assert hosting.evidence and hosting.evidence[0]["source"] == "knowledge"

    stripe = steps["credential:stripe"]
    assert stripe.payload["readiness"]["resolution"] == KNOWN
    assert stripe.payload["readiness"]["source"] == "integrations"

    assert readiness_satisfied(db_session, run) is True


def test_genuine_gap_becomes_waiting_approval(db_session):
    plan = {
        "requirements": [
            {
                "key": "launch_date",
                "question": "What is the launch date?",
                "kind": "decision",
                "keywords": ["launch", "date"],
            }
        ]
    }
    run = evaluate_readiness(db_session, plan=plan)

    step = _by_key(db_session, run)["launch_date"]
    assert step.status == WAITING_APPROVAL
    assert step.payload["readiness"]["resolution"] == NEEDS_USER

    # The gap surfaces in the existing approval queue (waiting_approval steps).
    assessment = readiness_assessment(db_session, run)
    assert assessment["blocking_open"] == ["launch_date"]


def test_unknown_non_blocking_is_flagged_not_gated(db_session):
    plan = {
        "requirements": [
            {
                "key": "nice_to_have",
                "question": "Any preferred font?",
                "kind": "preference",
                "blocking": False,
                "keywords": ["font", "typeface"],
            }
        ]
    }
    run = evaluate_readiness(db_session, plan=plan)

    step = _by_key(db_session, run)["nice_to_have"]
    # Surfaced as a flag, never at the gate, and never blocking.
    assert step.status == PLANNED
    assert step.payload["readiness"]["resolution"] == UNKNOWN
    assert readiness_satisfied(db_session, run) is True


def test_satisfied_false_while_blocking_open_then_true_once_resolved(db_session):
    plan = {
        "requirements": [
            {
                "key": "budget",
                "question": "What is the budget?",
                "kind": "decision",
                "keywords": ["budget"],
            }
        ]
    }
    run = evaluate_readiness(db_session, plan=plan)
    assert readiness_satisfied(db_session, run) is False

    step = _by_key(db_session, run)["budget"]
    resolve_approval(db_session, step, resolution="approved", note="USD 5000")

    assert readiness_satisfied(db_session, run) is True


def test_credential_item_never_writes_a_secret_to_a_step(db_session):
    secret = "sk_live_DO_NOT_LEAK"
    plan = {
        "requirements": [
            {
                "key": "sendgrid_key",
                "question": "SendGrid API key",
                "kind": "credential",
                "provider": "sendgrid",
            }
        ],
        # A raw secret carelessly placed on the plan: credential items resolve only from
        # connected integrations, so this value must never reach a step.
        "answers": {"sendgrid_key": secret},
    }
    run = evaluate_readiness(db_session, plan=plan)

    step = _by_key(db_session, run)["sendgrid_key"]
    assert step.status == WAITING_APPROVAL
    assert step.payload["readiness"]["resolution"] == NEEDS_CREDENTIAL

    for step in readiness_steps(db_session, run):
        blob = json.dumps(
            {
                "payload": step.payload,
                "evidence": step.evidence,
                "approval": step.approval,
                "intent": step.intent,
                "outcome": step.outcome,
            }
        )
        assert secret not in blob


def test_connected_credential_records_reference_not_secret(db_session):
    user = _user(db_session)
    db_session.add(
        Integration(
            user_id=user.id,
            provider="stripe",
            status="connected",
            credentials_ref="vault://stripe/key",
        )
    )
    db_session.commit()

    plan = {"integrations": ["stripe"]}
    run = evaluate_readiness(db_session, plan=plan)

    step = _by_key(db_session, run)["credential:stripe"]
    assert step.payload["readiness"]["resolution"] == KNOWN
    evidence = step.evidence[0]
    # Only the reference and provider are recorded, never a secret value.
    assert evidence["credentials_ref"] == "vault://stripe/key"
    assert evidence["provider"] == "stripe"


def test_resolved_readiness_answers_flow_into_agent_context(db_session):
    _know(db_session, "The brand color is orange, the only brand color.")
    plan = {
        "requirements": [
            {
                "key": "brand_color",
                "question": "What is the brand color?",
                "kind": "decision",
                "keywords": ["brand", "color"],
            },
            {
                "key": "domain",
                "question": "What domain should we use?",
                "kind": "decision",
                "keywords": ["domain"],
            },
        ]
    }
    run = evaluate_readiness(db_session, plan=plan)

    # Answer the open gap by approving it, the way a human would in the approval queue.
    gap = _by_key(db_session, run)["domain"]
    resolve_approval(db_session, gap, resolution="approved", note="nexaos.app")

    agent_run = create_run(db_session, autonomy_level=1)
    summary = inject_context(db_session, agent_run)

    assert "Resolved readiness answers" in summary
    assert "What is the brand color?" in summary  # resolved from a knowledge source
    assert "nexaos.app" in summary  # answered by the human at the gate
