"""Bounded agent context injection."""

from app.agents.context import MAX_CONTEXT_TOKENS, estimate_tokens, inject_context
from app.models.knowledge import KnowledgeEntry
from app.models.workspace import AppSetting
from app.runtime import (
    correct_step,
    create_run,
    propose_step,
    record_execution,
    resolve_approval,
)


def _seed_knowledge(db, scope, status, count, marker):
    for i in range(count):
        db.add(
            KnowledgeEntry(
                kind="rule",
                scope=scope,
                source="manual",
                content=f"{marker} entry {i} " + ("x" * 2000),
                confidence=0.9,
                status=status,
                provenance={},
            )
        )
    db.commit()


def test_inject_context_stays_within_token_limit(db_session):
    # Far more active knowledge and instruction text than can fit, to force the guard.
    db_session.add(
        AppSetting(key="general", value={"general_instructions": "Operate carefully. " * 300})
    )
    _seed_knowledge(db_session, "development", "active", 60, "DEVKNOW")
    _seed_knowledge(db_session, "general", "active", 60, "GENKNOW")
    db_session.commit()

    # A sample agent run: inject the context the next agent call would receive.
    run = create_run(db_session, autonomy_level=1)
    summary = inject_context(db_session, run)

    assert summary
    assert estimate_tokens(summary) <= MAX_CONTEXT_TOKENS
    db_session.refresh(run)
    assert run.context_summary == summary


def test_inject_context_only_active_development_and_general(db_session):
    db_session.add(
        KnowledgeEntry(
            kind="fact", scope="development", source="manual",
            content="ACTIVE_DEV_FACT", confidence=0.9, status="active", provenance={},
        )
    )
    db_session.add(
        KnowledgeEntry(
            kind="fact", scope="development", source="manual",
            content="ARCHIVED_DEV_FACT", confidence=0.9, status="archived", provenance={},
        )
    )
    db_session.add(
        KnowledgeEntry(
            kind="fact", scope="personal", source="manual",
            content="PERSONAL_FACT", confidence=0.9, status="active", provenance={},
        )
    )
    db_session.commit()

    run = create_run(db_session, autonomy_level=1)
    summary = inject_context(db_session, run)

    assert "ACTIVE_DEV_FACT" in summary
    assert "ARCHIVED_DEV_FACT" not in summary  # archived is excluded
    assert "PERSONAL_FACT" not in summary  # only development and general scopes are read


def test_inject_context_carries_rejections_and_corrections(db_session):
    gated_run = create_run(db_session, autonomy_level=0)
    gated = propose_step(db_session, gated_run, title="risky deploy", intent="deploy to prod")
    resolve_approval(db_session, gated, resolution="rejected", note="never deploy on a Friday")

    corrected_run = create_run(db_session, autonomy_level=1)
    step = propose_step(db_session, corrected_run, title="do the thing")
    record_execution(db_session, step, outcome="failed", failure={"error": "boom"})
    correct_step(db_session, step, status="skipped", correction_note="superseded by a safer path")

    run = create_run(db_session, autonomy_level=1)
    summary = inject_context(db_session, run)

    assert "never deploy on a Friday" in summary
    assert "superseded by a safer path" in summary
    assert estimate_tokens(summary) <= MAX_CONTEXT_TOKENS
