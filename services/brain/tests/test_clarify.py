"""Clarify stage: questions, integration match, plan update, and preview."""

import app.agents.clarify as clarify_mod
from app.agents.clarify import apply_clarify, get_clarify
from app.models.inbox import ClassificationRecord, InboxItem
from app.models.project import Integration, Project
from app.models.user import User
from app.settings import get_settings

PLAN = {
    "summary": "Launch site",
    "objective": "signups",
    "open_questions": ["which domain"],
    "workstreams": ["build"],
    "deliverables": ["page"],
    "likely_integrations": ["stripe", "mailchimp"],
    "proposed_build_destination": "vercel nexa",
}


def _setup(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_projects_root", str(tmp_path))
    user = User(email="cl@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    item = InboxItem(user_id=user.id, name="Launch site", body="b", status="routed",
                     stage_history=[])
    db_session.add(item)
    db_session.flush()
    db_session.add(
        ClassificationRecord(
            item_id=item.id, shape="project", confidence=0.9, recommended_route="project",
            recommended_model_key="agentic_code", resolved_model_id="x", model_rationale="r",
            reasoning_summary="s", tags=[],
        )
    )
    project = Project(item_id=item.id, name="Launch site", slug="launch-site", stage="process",
                      plan_json=PLAN, build_destination="vercel nexa")
    db_session.add(project)
    db_session.add(Integration(user_id=user.id, provider="stripe", status="connected"))
    db_session.commit()
    return item, user, project


def test_get_clarify_matches_integrations(db_session, tmp_path, monkeypatch):
    item, _, _ = _setup(db_session, tmp_path, monkeypatch)
    monkeypatch.setattr(
        clarify_mod, "synthesize_json",
        lambda key, prompt, schema=None: {"questions": ["What is the launch date?"]},
    )
    result = get_clarify(db_session, item)
    assert result["clarifying_questions"] == ["What is the launch date?"]
    by_provider = {s["provider"]: s for s in result["suggested_integrations"]}
    assert by_provider["stripe"]["status"] == "connected"
    assert by_provider["mailchimp"]["status"] == "available"


def test_apply_clarify_writes_files_and_persists(db_session, tmp_path, monkeypatch):
    item, _, project = _setup(db_session, tmp_path, monkeypatch)
    stripe = db_session.query(Integration).first()
    updated = apply_clarify(
        db_session, item,
        answers={"What is the launch date?": "July 1"},
        selected_integration_ids=[stripe.id],
        scope_changes={"build_destination": "netlify nexa"},
    )
    assert updated.selected_integrations == ["stripe"]
    assert updated.build_destination == "netlify nexa"
    assert updated.stage == "clarify"
    slug_dir = tmp_path / "launch-site"
    assert (slug_dir / "change_summary.md").exists()
    assert (slug_dir / "project_preview.html").exists()
    assert "Clarifications" in (slug_dir / "project_plan.md").read_text()


def test_clarify_endpoints(client, db_session, tmp_path, monkeypatch):
    item, _, _ = _setup(db_session, tmp_path, monkeypatch)
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    monkeypatch.setattr(
        clarify_mod, "synthesize_json", lambda key, prompt, schema=None: {"questions": ["q?"]}
    )
    headers = {"Authorization": "Bearer t"}

    got = client.get(f"/flow/items/{item.id}/clarify", headers=headers)
    assert got.status_code == 200
    assert got.json()["clarifying_questions"] == ["q?"]

    posted = client.post(
        f"/flow/items/{item.id}/clarify",
        json={"answers": {"q?": "a"}, "selected_integration_ids": [], "scope_changes": {}},
        headers=headers,
    )
    assert posted.status_code == 200

    preview = client.get(f"/flow/items/{item.id}/preview", headers=headers)
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("text/html")
    assert "<h1>" in preview.text
