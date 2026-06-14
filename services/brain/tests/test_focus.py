"""Focus: the operator view buckets and the explainable ranking.

Every test drives the real endpoints with the desktop bearer (which acts as the seed user) and
asserts the derived shape, never a stub. Timestamps are set explicitly to exercise the fixed
7 day stale threshold and the age factor.
"""

from datetime import timedelta

from app.models.base import utcnow
from app.models.dreaming import MemoryCandidate
from app.models.project import BuildLogEntry, PMRun, Project
from app.models.runtime import AgentRun, AgentStep
from app.models.workspace import Task
from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}

# A fully safe-set step risk classification (see app.gates): an agent could take it if autonomy
# were raised, so the approval is autonomy eligible.
SAFE_RISK = {"low_risk": True, "reversible": True, "local": True, "non_external": True}
# Materially affects the outcome: a gate that genuinely needs the human.
UNSAFE_RISK = {**SAFE_RISK, "external": True}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


def test_empty_state_is_honest(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    operator = client.get("/focus/operator", headers=BEARER).json()
    assert operator["approvals_waiting"] == []
    assert operator["stale_projects"] == []
    assert operator["blocked_work"] == []
    assert operator["tasks_safe_to_complete"] == []
    assert operator["recommended_next_actions"] == []
    assert operator["stale_threshold_days"] == 7

    ranked = client.get("/focus/ranked", headers=BEARER).json()
    assert ranked["actions"] == []
    assert ranked["stale_threshold_days"] == 7


def test_build_at_gate_is_an_approval(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    project = Project(item_id=None, name="Gatekeeper", slug="gatekeeper", stage="clarify")
    db_session.add(project)
    db_session.commit()

    operator = client.get("/focus/operator", headers=BEARER).json()
    approvals = operator["approvals_waiting"]
    assert len(approvals) == 1
    assert approvals[0]["kind"] == "approve_build"
    # Every item links to its source.
    assert approvals[0]["source"] == {"type": "project", "id": project.id}

    # It also appears in the ranked list with a reason that explains its rank.
    ranked = client.get("/focus/ranked", headers=BEARER).json()["actions"]
    top = next(a for a in ranked if a["kind"] == "approve_build")
    assert top["factors"]["risk"] == "high"
    assert "risk" in top["reason"]


def test_stale_threshold_is_seven_days(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    old = utcnow() - timedelta(days=8)
    fresh = utcnow() - timedelta(days=2)
    stale = Project(
        item_id=None, name="Stalled", slug="stalled", stage="build", updated_at=old
    )
    recent = Project(
        item_id=None, name="Moving", slug="moving", stage="build", updated_at=fresh
    )
    db_session.add_all([stale, recent])
    db_session.commit()

    operator = client.get("/focus/operator", headers=BEARER).json()
    stale_names = {i["title"] for i in operator["stale_projects"]}
    assert "Advance Stalled" in stale_names
    assert "Advance Moving" not in stale_names
    item = next(i for i in operator["stale_projects"] if i["title"] == "Advance Stalled")
    assert item["age_days"] >= 7
    assert item["source"] == {"type": "project", "id": stale.id}


def test_active_run_keeps_old_project_off_the_stale_list(
    client, seed_user, db_session, monkeypatch
):
    _enable_bearer(monkeypatch)
    old = utcnow() - timedelta(days=20)
    project = Project(
        item_id=None, name="Live build", slug="live-build", stage="build", updated_at=old
    )
    db_session.add(project)
    db_session.commit()
    # A run in flight on the project means it is progressing, not stale.
    db_session.add(AgentRun(project_id=project.id, status="executing"))
    db_session.commit()

    operator = client.get("/focus/operator", headers=BEARER).json()
    assert all(i["source"]["id"] != project.id for i in operator["stale_projects"])


def test_blocked_and_safe_tasks_split_into_buckets(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    db_session.add_all(
        [
            Task(user_id=seed_user.id, title="stuck", status="blocked"),
            Task(user_id=seed_user.id, title="do me", status="open"),
            Task(user_id=seed_user.id, title="gone", status="open", deleted_at=utcnow()),
            Task(user_id=seed_user.id, title="finished", status="done"),
        ]
    )
    db_session.commit()

    operator = client.get("/focus/operator", headers=BEARER).json()
    blocked_titles = {i["title"] for i in operator["blocked_work"]}
    safe_titles = {i["title"] for i in operator["tasks_safe_to_complete"]}
    assert "Unblock task: stuck" in blocked_titles
    assert "Complete: do me" in safe_titles
    # Soft deleted and done tasks never surface.
    assert not any("gone" in t for t in safe_titles | blocked_titles)
    assert not any("finished" in t for t in safe_titles | blocked_titles)


def test_run_approval_autonomy_eligibility(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    # A safe-set gate: autonomy eligible, low risk.
    safe_run = AgentRun(project_id=None, status="waiting_approval", autonomy_level=0)
    db_session.add(safe_run)
    db_session.commit()
    db_session.add(
        AgentStep(run_id=safe_run.id, seq=1, status="waiting_approval", payload={"risk": SAFE_RISK})
    )
    # A gate that materially affects the outcome: not eligible, high risk.
    risky_run = AgentRun(project_id=None, status="waiting_approval", autonomy_level=0)
    db_session.add(risky_run)
    db_session.commit()
    db_session.add(
        AgentStep(
            run_id=risky_run.id, seq=1, status="waiting_approval", payload={"risk": UNSAFE_RISK}
        )
    )
    db_session.commit()

    ranked = client.get("/focus/ranked", headers=BEARER).json()["actions"]
    by_source = {a["source"]["id"]: a for a in ranked if a["source"]["type"] == "run"}
    assert by_source[safe_run.id]["factors"]["autonomy_eligible"] is True
    assert by_source[safe_run.id]["factors"]["risk"] == "low"
    assert by_source[risky_run.id]["factors"]["autonomy_eligible"] is False
    assert by_source[risky_run.id]["factors"]["risk"] == "high"
    # The safe-set, delegable gate ranks below the risky one despite both being approvals.
    assert risky_run.id != safe_run.id
    assert by_source[risky_run.id]["score"] > by_source[safe_run.id]["score"]


def test_pending_memory_candidates_aggregate(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    db_session.add_all(
        [
            MemoryCandidate(facet="about_user", kind="fact", scope="general", content="a"),
            MemoryCandidate(facet="about_user", kind="fact", scope="general", content="b"),
        ]
    )
    db_session.commit()

    operator = client.get("/focus/operator", headers=BEARER).json()
    memory = [i for i in operator["approvals_waiting"] if i["kind"] == "review_memory"]
    assert len(memory) == 1
    assert "2 memory candidates" in memory[0]["title"]
    assert memory[0]["source"] == {"type": "dreaming", "id": None}


def test_blocked_outranks_safe_task(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    db_session.add_all(
        [
            Task(user_id=seed_user.id, title="stuck", status="blocked"),
            Task(user_id=seed_user.id, title="easy", status="open"),
        ]
    )
    db_session.commit()

    ranked = client.get("/focus/ranked", headers=BEARER).json()["actions"]
    ranks = {a["kind"]: a["rank"] for a in ranked}
    assert ranks["unblock_task"] < ranks["complete_task"]
    # The recommended list is the head of the ranking.
    recommended = client.get("/focus/operator", headers=BEARER).json()["recommended_next_actions"]
    assert recommended[0]["rank"] == 1


def test_proposed_edit_and_pm_managed_detail(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    old = utcnow() - timedelta(days=10)
    project = Project(
        item_id=None, name="Managed", slug="managed", stage="build", updated_at=old
    )
    db_session.add(project)
    db_session.commit()
    db_session.add_all(
        [
            PMRun(project_id=project.id, status="active"),
            BuildLogEntry(
                project_id=project.id, action="edit", status="proposed", summary="tweak header"
            ),
        ]
    )
    db_session.commit()

    operator = client.get("/focus/operator", headers=BEARER).json()
    edits = [i for i in operator["approvals_waiting"] if i["kind"] == "review_edit"]
    assert edits and edits[0]["source"] == {"type": "project", "id": project.id}
    stale = next(i for i in operator["stale_projects"] if i["source"]["id"] == project.id)
    assert "project manager run" in stale["detail"]
