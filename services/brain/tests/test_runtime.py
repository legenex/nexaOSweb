"""Runtime authorship, verification, transition, and cache guarantees.

These tests pin the honesty rules of the runtime: that each writer authors only its own slice
of a step, that a verified outcome is earned from tool evidence and never asserted, that the
transition table is enforced, that terminal states move only through the named correction, and
that the cached run status is always the pure derivation of its steps.
"""

from types import SimpleNamespace

import pytest

from app.models.runtime import AgentStep
from app.runtime import (
    BLOCKED,
    COMPLETED_UNVERIFIED,
    COMPLETED_VERIFIED,
    EXECUTING,
    FAILED,
    PLANNED,
    SKIPPED,
    WAITING_APPROVAL,
    RuntimeWriteError,
    correct_step,
    create_run,
    derive_run_status,
    propose_step,
    record_execution,
    resolve_approval,
    transition_allowed,
)
from app.settings import get_settings


def _steps(db, run):
    return db.query(AgentStep).filter(AgentStep.run_id == run.id).order_by(AgentStep.seq).all()


def _assert_cache_is_derivation(db, run):
    db.refresh(run)
    assert run.status == derive_run_status(_steps(db, run))


# --- authorship split: propose_step ------------------------------------------------------


def test_propose_step_authors_intent_only(db_session):
    gated = create_run(db_session, autonomy_level=0)
    step = propose_step(db_session, gated, kind="edit", title="Edit a file", intent="do it")
    # The entry gate placed it at waiting_approval, and no outcome field was authored.
    assert step.status == WAITING_APPROVAL
    assert step.evidence == []
    assert step.tool_call is None
    assert step.failure is None
    assert step.approval is None
    assert step.correction_note is None
    assert step.corrected_from is None

    # The entry gate is deny-by-default. At a higher autonomy level a step auto-resolves to
    # planned only when it carries an explicit safe classification; see test_gates.py.
    autonomous = create_run(db_session, autonomy_level=2)
    safe_risk = {"low_risk": True, "reversible": True, "local": True, "non_external": True}
    ungated = propose_step(db_session, autonomous, title="No gate", payload={"risk": safe_risk})
    assert ungated.status == PLANNED
    # Without a safe classification, even an autonomous run keeps the step gated.
    still_gated = propose_step(db_session, autonomous, title="Unclassified")
    assert still_gated.status == WAITING_APPROVAL


def test_propose_step_cannot_set_protected_fields(db_session):
    run = create_run(db_session, autonomy_level=1)
    # propose_step has no parameter for any of these; passing one is a hard TypeError.
    for kwarg in (
        {"status": "executing"},
        {"tool_call": {"name": "x"}},
        {"evidence": [{"source": "tool"}]},
        {"failure": {"error": "x"}},
        {"approval": {"resolution": "approved"}},
    ):
        with pytest.raises(TypeError):
            propose_step(db_session, run, title="x", **kwarg)


# --- verification is derived, never asserted ---------------------------------------------


def test_record_execution_derives_unverified_without_tool_evidence(db_session):
    run = create_run(db_session, autonomy_level=1)
    for source in ("llm", "user"):
        step = propose_step(db_session, run, title=f"{source} only")
        done = record_execution(
            db_session, step, outcome="completed", evidence=[{"source": source, "note": "x"}]
        )
        assert done.status == COMPLETED_UNVERIFIED


def test_record_execution_derives_verified_with_tool_evidence(db_session):
    run = create_run(db_session, autonomy_level=1)
    step = propose_step(db_session, run, title="ran a tool")
    done = record_execution(
        db_session,
        step,
        outcome="completed",
        evidence=[{"source": "llm", "note": "reasoned"}, {"source": "tool", "exit_code": 0}],
        tool_call={"name": "shell", "args": ["ls"]},
    )
    assert done.status == COMPLETED_VERIFIED


def test_verified_is_never_a_settable_target(db_session):
    run = create_run(db_session, autonomy_level=1)
    step = propose_step(db_session, run, title="x")
    with pytest.raises(RuntimeWriteError):
        record_execution(db_session, step, outcome="completed_verified", evidence=[])
    with pytest.raises(RuntimeWriteError):
        record_execution(db_session, step, outcome="completed_unverified", evidence=[])


# --- transition enforcement ---------------------------------------------------------------


def test_transition_table_rejects_illegal_edges():
    assert transition_allowed(PLANNED, EXECUTING)
    assert transition_allowed(EXECUTING, COMPLETED_VERIFIED)
    assert transition_allowed(WAITING_APPROVAL, PLANNED)
    # Illegal: no direct planned to verified, no leaving a terminal, no executing back to planned.
    assert not transition_allowed(PLANNED, COMPLETED_VERIFIED)
    assert not transition_allowed(EXECUTING, PLANNED)
    assert not transition_allowed(COMPLETED_UNVERIFIED, PLANNED)
    assert not transition_allowed(SKIPPED, EXECUTING)
    assert not transition_allowed(FAILED, EXECUTING)


def test_record_execution_cannot_mutate_a_terminal_step(db_session):
    run = create_run(db_session, autonomy_level=1)
    step = propose_step(db_session, run, title="x")
    record_execution(db_session, step, outcome="failed", failure={"error": "boom"})
    assert step.status == FAILED
    with pytest.raises(RuntimeWriteError):
        record_execution(db_session, step, outcome="completed", evidence=[{"source": "tool"}])


def test_resolve_approval_requires_waiting_approval(db_session):
    run = create_run(db_session, autonomy_level=1)
    # A safe classification auto-resolves the step to planned, so it is not at the gate.
    safe_risk = {"low_risk": True, "reversible": True, "local": True, "non_external": True}
    step = propose_step(db_session, run, title="x", payload={"risk": safe_risk})
    assert step.status == PLANNED
    with pytest.raises(RuntimeWriteError):
        resolve_approval(db_session, step, resolution="approved")


def test_resolve_approval_owns_only_the_exit_edges(db_session):
    run = create_run(db_session, autonomy_level=0)
    approved = propose_step(db_session, run, title="approve me")
    resolve_approval(db_session, approved, resolution="approved", resolved_by="nick")
    assert approved.status == PLANNED
    assert approved.approval["resolution"] == "approved"

    rejected = propose_step(db_session, run, title="reject me")
    resolve_approval(db_session, rejected, resolution="rejected")
    assert rejected.status == SKIPPED


# --- correction is the only terminal mutation --------------------------------------------


def test_correct_step_changes_status_only_with_an_audit_note(db_session):
    run = create_run(db_session, autonomy_level=1)
    step = propose_step(db_session, run, kind="deploy", title="ship it", intent="deploy build")
    record_execution(db_session, step, outcome="failed", failure={"error": "timeout"})
    intent_before = (step.kind, step.title, step.intent, list(step.evidence))

    corrected = correct_step(
        db_session,
        step,
        status=COMPLETED_UNVERIFIED,
        correction_note="verified out of band, the deploy did land",
    )
    assert corrected.status == COMPLETED_UNVERIFIED
    assert corrected.corrected_from == FAILED
    assert "out of band" in corrected.correction_note
    # Intent and recorded outcome are untouched: correction changes status only.
    assert (corrected.kind, corrected.title, corrected.intent, list(corrected.evidence)) == (
        intent_before
    )


def test_correct_step_guards(db_session):
    run = create_run(db_session, autonomy_level=1)
    planned = propose_step(db_session, run, title="x")
    # Cannot correct a non-terminal step.
    with pytest.raises(RuntimeWriteError):
        correct_step(db_session, planned, status=FAILED, correction_note="n")

    record_execution(db_session, planned, outcome="failed", failure={"e": 1})
    # Cannot set the derived verified status, and a note is required.
    with pytest.raises(RuntimeWriteError):
        correct_step(db_session, planned, status=COMPLETED_VERIFIED, correction_note="n")
    with pytest.raises(RuntimeWriteError):
        correct_step(db_session, planned, status=COMPLETED_UNVERIFIED, correction_note="   ")


# --- the cached run status is always the pure derivation ----------------------------------


def test_cached_run_status_tracks_derivation_after_every_writer(db_session):
    run = create_run(db_session, autonomy_level=0)
    _assert_cache_is_derivation(db_session, run)  # no steps -> planned

    a = propose_step(db_session, run, title="a")  # waiting_approval
    _assert_cache_is_derivation(db_session, run)
    assert run.status == WAITING_APPROVAL

    resolve_approval(db_session, a, resolution="approved")  # -> planned
    _assert_cache_is_derivation(db_session, run)

    record_execution(db_session, a, outcome="completed", evidence=[{"source": "tool"}])
    _assert_cache_is_derivation(db_session, run)

    b = propose_step(db_session, run, title="b")  # waiting_approval again
    _assert_cache_is_derivation(db_session, run)
    resolve_approval(db_session, b, resolution="approved")
    record_execution(db_session, b, outcome="failed", failure={"e": 1})
    _assert_cache_is_derivation(db_session, run)
    assert run.status == "failed"

    correct_step(db_session, b, status=SKIPPED, correction_note="not needed after all")
    _assert_cache_is_derivation(db_session, run)
    # a is completed_verified, b is now skipped: all terminal, none failed -> completed.
    assert run.status == "completed"


# --- run status derivation, in isolation --------------------------------------------------


def test_run_status_derives_from_step_statuses():
    def run_of(*statuses):
        return derive_run_status([SimpleNamespace(status=s) for s in statuses])

    assert run_of() == "planned"
    assert run_of(EXECUTING, COMPLETED_VERIFIED) == "executing"
    assert run_of(WAITING_APPROVAL, PLANNED) == "waiting_approval"
    assert run_of(BLOCKED, COMPLETED_UNVERIFIED) == "blocked"
    assert run_of(PLANNED, COMPLETED_VERIFIED) == "planned"
    assert run_of(COMPLETED_VERIFIED, COMPLETED_UNVERIFIED, SKIPPED) == "completed"
    assert run_of(COMPLETED_VERIFIED, FAILED) == "failed"


# --- large evidence is stored by reference under the runtime root -------------------------


def test_large_tool_output_spills_to_content_ref(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_runtime_root", str(tmp_path))
    run = create_run(db_session, autonomy_level=1)
    step = propose_step(db_session, run, title="big output")
    big = "x" * 9000
    done = record_execution(
        db_session,
        step,
        outcome="completed",
        evidence=[{"source": "tool", "content": big}, {"source": "llm", "content": "small"}],
    )
    tool_item = done.evidence[0]
    assert "content" not in tool_item
    assert tool_item["content_ref"].startswith(f"run_{run.id}/")
    assert tool_item["content_bytes"] == 9000
    assert (tmp_path / tool_item["content_ref"]).read_text() == big
    # The small llm item stays inline.
    assert done.evidence[1]["content"] == "small"
    assert done.status == COMPLETED_VERIFIED
