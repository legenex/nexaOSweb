"""Dashboard summary aggregates real data; the brief is cached per day and refreshable."""

from app.models.dreaming import DreamRun
from app.models.inbox import ClassificationRecord, InboxItem
from app.models.knowledge import KnowledgeEntry
from app.models.project import Integration, Project
from app.models.workspace import Task
from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


def _seed(db, user):
    promoted = InboxItem(user_id=user.id, name="Launch tracker", source="note", status="processed")
    finding = InboxItem(user_id=user.id, name="Pricing scan", source="url", status="classified")
    db.add_all([promoted, finding])
    db.flush()
    db.add_all(
        [
            ClassificationRecord(
                item_id=promoted.id, shape="project", confidence=0.88,
                recommended_route="project_build", recommended_model_key="agentic_code",
                resolved_model_id="anthropic/claude-opus-4-8",
            ),
            ClassificationRecord(
                item_id=finding.id, shape="content", confidence=0.74,
                recommended_route="research", recommended_model_key="research_synthesis",
                resolved_model_id="anthropic/claude-sonnet-4-6",
            ),
        ]
    )
    db.add_all(
        [
            Project(item_id=promoted.id, name="Launch tracker", slug="launch", stage="build"),
            Project(item_id=None, name="Pricing one pager", slug="pricing", stage="clarify"),
        ]
    )
    db.add_all(
        [
            Task(user_id=user.id, title="Wire the UI", status="open"),
            Task(user_id=user.id, title="Old thing", status="done"),
        ]
    )
    db.add(Integration(user_id=user.id, provider="github", status="connected"))
    db.add(
        KnowledgeEntry(
            kind="preference", scope="general", source="dreaming",
            content="Likes terse briefs.", confidence=0.8, status="active", provenance={},
        )
    )
    db.add(
        DreamRun(
            status="completed", trigger="scheduled", model_key="bulk",
            items_considered=4, candidates_created=2,
        )
    )
    db.commit()


def test_summary_returns_real_aggregate(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    _seed(db_session, seed_user)

    body = client.get("/dashboard/summary", headers=BEARER).json()

    assert body["active_projects_count"] == 1
    assert body["active_projects"][0]["name"] == "Launch tracker"
    assert body["builds_awaiting_approval_count"] == 1
    assert body["builds_awaiting_approval"][0]["stage"] == "clarify"
    # The classified capture with no project is a research finding ready to convert.
    assert body["research_ready_count"] == 1
    assert body["research_ready"][0]["shape"] == "content"
    assert body["suggested_tasks_count"] == 1
    assert body["top_opportunity"]["title"].startswith("Approve")
    assert any(c["provider"] == "github" for c in body["connector_health"])
    keys = {usage["model_key"] for usage in body["model_usage"]}
    assert {"agentic_code", "research_synthesis", "bulk"} <= keys
    assert body["brain"]["status"] == "ok"
    assert body["brain"]["last_dream_at"] is not None


def test_brief_is_cached_and_refreshable(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    _seed(db_session, seed_user)

    first = client.get("/dashboard/brief?mode=morning", headers=BEARER).json()
    assert first["mode"] == "morning"
    assert first["cached"] is False
    assert first["text"]

    # A second open returns the cached brief, unchanged.
    second = client.get("/dashboard/brief?mode=morning", headers=BEARER).json()
    assert second["cached"] is True
    assert second["generated_at"] == first["generated_at"]
    assert second["text"] == first["text"]

    # A manual refresh regenerates.
    refreshed = client.get("/dashboard/brief?mode=morning&refresh=true", headers=BEARER).json()
    assert refreshed["cached"] is False

    # Evening is a separate cache entry with its own text.
    evening = client.get("/dashboard/brief?mode=evening", headers=BEARER).json()
    assert evening["mode"] == "evening"
    assert evening["cached"] is False
    assert evening["text"] != first["text"]


def test_brief_offline_text_reflects_counts(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    _seed(db_session, seed_user)
    body = client.get("/dashboard/brief?mode=morning", headers=BEARER).json()
    # Offline rendering names the focus and the dreaming candidate count.
    assert "Approve" in body["text"]
    assert "2 memory candidates" in body["text"]
