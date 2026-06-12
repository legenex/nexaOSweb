"""Flow aggregator and settings, completing the v1 contract."""

from app.models.inbox import ClassificationRecord, InboxItem
from app.models.project import Project
from app.models.user import User
from app.settings import get_settings


def _item_with_project(db_session, tmp_path):
    settings = get_settings()
    settings.nexa_projects_root = str(tmp_path)
    user = db_session.query(User).first()
    if user is None:
        user = User(email="agg@example.com", password_hash="x")
        db_session.add(user)
        db_session.flush()
    item = InboxItem(user_id=user.id, name="Site", body="b", status="routed", stage_history=[])
    db_session.add(item)
    db_session.flush()
    db_session.add(
        ClassificationRecord(
            item_id=item.id, shape="project", confidence=0.9, recommended_route="project",
            recommended_model_key="agentic_code", resolved_model_id="x", model_rationale="r",
            reasoning_summary="s", tags=["web"],
        )
    )
    slug = "site"
    plan_dir = tmp_path / slug
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "project_plan.md").write_text("# Site\n")
    (plan_dir / "project_preview.html").write_text("<html></html>")
    db_session.add(
        Project(
            item_id=item.id, name="Site", slug=slug, stage="approved",
            plan_path=str(plan_dir / "project_plan.md"), build_destination="vercel",
            selected_integrations=["stripe"],
        )
    )
    db_session.commit()
    return item


def test_flow_item_dto(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    item = _item_with_project(db_session, tmp_path)
    headers = {"Authorization": "Bearer t"}

    single = client.get(f"/flow/items/{item.id}", headers=headers).json()
    assert single["route"] == "project"
    assert single["project_stage"] == "approved"
    assert single["plan_available"] is True
    assert single["preview_available"] is True
    assert single["gate_state"] == "approved"
    assert single["build_destination"] == "vercel"
    assert single["selected_integrations"] == ["stripe"]
    assert single["classification"]["shape"] == "project"

    listing = client.get("/flow/items", headers=headers).json()
    assert any(entry["id"] == item.id for entry in listing)


def test_settings_get_and_patch(client, seed_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    headers = {"Authorization": "Bearer t"}

    current = client.get("/settings", headers=headers).json()
    assert "confidence_threshold" in current
    assert current["classify_batch"] >= 1

    patched = client.patch(
        "/settings",
        json={"confidence_threshold": 0.8, "classify_sweep_enabled": True},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["confidence_threshold"] == 0.8
    assert patched.json()["classify_sweep_enabled"] is True

    # Persisted across reads.
    again = client.get("/settings", headers=headers).json()
    assert again["confidence_threshold"] == 0.8
