"""Insights generation from the Knowledge base and recent activity, plus the actions."""

from app.models.inbox import ClassificationRecord, InboxItem
from app.models.insight import Insight
from app.models.knowledge import KnowledgeEntry
from app.models.project import Integration, Project
from app.models.workspace import JournalNote
from app.settings import get_settings

BEARER = {"Authorization": "Bearer t"}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")


def _seed(db, user):
    # Knowledge across scopes so personal and work patterns both derive.
    db.add(KnowledgeEntry(
        kind="preference", scope="personal", source="manual",
        content="Prefers deep work in the early morning", confidence=0.8, status="active",
        provenance={},
    ))
    db.add(KnowledgeEntry(
        kind="pattern", scope="development", source="dreaming",
        content="Ships in small, frequent increments", confidence=0.7, status="active",
        provenance={},
    ))
    # Two projects, both app mode, so the mode pattern derives.
    db.add(Project(item_id=None, name="Landing page", slug="landing-page", stage="build",
                   mode="app", workspace={"revenue_potential": "subscriptions"}))
    db.add(Project(item_id=None, name="Internal tool", slug="internal-tool", stage="idea",
                   mode="app", workspace={}))
    # An unconverted capture (no project) to seed a project idea.
    item = InboxItem(user_id=user.id, name="Newsletter idea", body="weekly digest",
                     source="note", status="classified", stage_history=[])
    db.add(item)
    db.flush()
    db.add(ClassificationRecord(
        item_id=item.id, shape="project", confidence=0.9, recommended_route="project",
        recommended_model_key="agentic_code", resolved_model_id="x", model_rationale="r",
        reasoning_summary="s", tags=[],
    ))
    db.add(JournalNote(user_id=user.id, body="Reflected on the week."))
    # Two connected integrations seed an automation idea.
    db.add(Integration(user_id=user.id, provider="github", status="connected"))
    db.add(Integration(user_id=user.id, provider="clickup", status="connected"))
    db.commit()


def test_generation_uses_both_semantic_keys(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    _seed(db_session, seed_user)
    seen: list[str] = []

    def recording_text(key, prompt, system=None):
        seen.append(key)
        return None  # force the deterministic fallback so content is reproducible

    import app.agents.insights as insights_mod
    monkeypatch.setattr(insights_mod, "synthesize_text", recording_text)

    res = client.get("/insights", headers=BEARER)
    assert res.status_code == 200
    body = res.json()
    # Extraction ran on bulk, the profile pass on research_synthesis.
    assert "bulk" in seen
    assert "research_synthesis" in seen
    assert body["extraction_model_key"] == "bulk"
    assert body["synthesis_model_key"] == "research_synthesis"


def test_insights_generate_from_real_data_with_required_fields(
    client, seed_user, db_session, monkeypatch
):
    _enable_bearer(monkeypatch)
    _seed(db_session, seed_user)
    body = client.get("/insights", headers=BEARER).json()

    assert body["personal_patterns"], "expected personal patterns from knowledge/activity"
    assert body["work_patterns"], "expected work patterns from knowledge/activity"
    assert body["profile_summary"] is not None
    assert body["innovation"], "expected an innovation feed"

    # Every insight carries confidence, source, and reasoning.
    flat = (
        body["personal_patterns"]
        + body["work_patterns"]
        + [body["profile_summary"]]
        + body["innovation"]
    )
    for ins in flat:
        assert 0.0 <= ins["confidence"] <= 1.0
        assert ins["source"]
        assert ins["reasoning"]

    # The innovation feed spans the idea kinds derived from the seeded signals.
    idea_kinds = {i["idea_kind"] for i in body["innovation"]}
    assert {"project", "revenue", "automation"} <= idea_kinds

    # A work pattern reflects the real project mode mix.
    titles = " ".join(w["title"] for w in body["work_patterns"]).lower()
    assert "app" in titles


def test_refresh_supersedes_prior_batch(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    _seed(db_session, seed_user)
    first = client.get("/insights", headers=BEARER).json()
    second = client.post("/insights/refresh", headers=BEARER).json()
    assert second["run_id"] != first["run_id"]

    # The prior batch's insights are superseded, not deleted.
    superseded = (
        db_session.query(Insight)
        .filter(Insight.run_id == first["run_id"], Insight.status == "superseded")
        .count()
    )
    assert superseded > 0
    # The cached read now returns the latest run.
    assert client.get("/insights", headers=BEARER).json()["run_id"] == second["run_id"]


def test_action_save_to_knowledge(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    _seed(db_session, seed_user)
    body = client.get("/insights", headers=BEARER).json()
    insight = body["personal_patterns"][0]

    res = client.post(f"/insights/{insight['id']}/save-to-knowledge", headers=BEARER)
    assert res.status_code == 201
    entry_id = res.json()["knowledge_entry_id"]
    entry = db_session.get(KnowledgeEntry, entry_id)
    assert entry.provenance["from"] == "insight"
    assert entry.scope == "personal"

    # Acting twice is a conflict.
    again = client.post(f"/insights/{insight['id']}/save-to-knowledge", headers=BEARER)
    assert again.status_code == 409


def test_action_create_task_and_project(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    _seed(db_session, seed_user)
    body = client.get("/insights", headers=BEARER).json()
    idea = next(i for i in body["innovation"] if i["idea_kind"] == "project")
    work = body["work_patterns"][0]

    task = client.post(f"/insights/{work['id']}/create-task", headers=BEARER)
    assert task.status_code == 201
    assert task.json()["task_id"]

    project = client.post(f"/insights/{idea['id']}/create-project", headers=BEARER)
    assert project.status_code == 201
    new_project = db_session.get(Project, project.json()["project_id"])
    assert new_project is not None
    assert new_project.plan_json["objective"]


def test_action_dismiss_removes_from_feed(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    _seed(db_session, seed_user)
    body = client.get("/insights", headers=BEARER).json()
    insight = body["innovation"][0]

    dismissed = client.post(f"/insights/{insight['id']}/dismiss", headers=BEARER)
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    after = client.get("/insights", headers=BEARER).json()
    ids = {i["id"] for i in after["innovation"]}
    assert insight["id"] not in ids
