"""Process stage builds the folder and plan."""

import app.agents.process as process_mod
from app.agents.process import process_item, render_plan_markdown
from app.models.inbox import ClassificationRecord, InboxItem
from app.models.project import Project
from app.models.user import User
from app.settings import get_settings

PLAN = {
    "summary": "Build a launch landing page",
    "objective": "Drive signups",
    "recommended_outcome": "A live page",
    "project_tree": ["index.html", "styles.css"],
    "workstreams": ["design", "build"],
    "deliverables": ["landing page"],
    "subtasks": ["wire the form"],
    "dependencies": ["brand assets"],
    "assets": ["logo"],
    "owners": ["nick"],
    "open_questions": ["which domain"],
    "risks": ["scope creep"],
    "estimated_complexity": "medium",
    "recommended_next_steps": ["clarify integrations"],
    "proposed_build_destination": "vercel project nexa-launch",
    "likely_integrations": ["stripe", "mailchimp"],
}


def _project_item(db_session):
    user = User(email="p@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    item = InboxItem(
        user_id=user.id, name="Launch landing page", body="for the product",
        status="routed", stage_history=[],
    )
    db_session.add(item)
    db_session.flush()
    db_session.add(
        ClassificationRecord(
            item_id=item.id, shape="project", confidence=0.9, recommended_route="project",
            recommended_model_key="agentic_code", resolved_model_id="x", model_rationale="r",
            reasoning_summary="s", tags=["web"],
        )
    )
    project = Project(item_id=item.id, name="Launch landing page", slug="launch-landing-page",
                      stage="idea")
    db_session.add(project)
    db_session.commit()
    return item, user


def test_render_plan_markdown_has_sections():
    md = render_plan_markdown("My Project", PLAN)
    assert "# My Project" in md
    assert "## Summary" in md
    assert "- stripe" in md


def test_process_writes_plan(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "nexa_projects_root", str(tmp_path))
    monkeypatch.setattr(process_mod, "synthesize_json", lambda key, prompt, schema=None: PLAN)
    item, _ = _project_item(db_session)

    project = process_item(db_session, item)
    assert project.plan_json["summary"] == "Build a launch landing page"
    assert project.build_destination == "vercel project nexa-launch"
    assert project.stage == "process"
    written = tmp_path / "launch-landing-page" / "project_plan.md"
    assert written.exists()
    assert "## Workstreams" in written.read_text()


def test_process_endpoint_and_plan_stream(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "nexa_projects_root", str(tmp_path))
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    monkeypatch.setattr(process_mod, "synthesize_json", lambda key, prompt, schema=None: PLAN)
    item, _ = _project_item(db_session)
    headers = {"Authorization": "Bearer t"}

    resp = client.post(f"/flow/items/{item.id}/process", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["build_destination"] == "vercel project nexa-launch"

    plan = client.get(f"/flow/items/{item.id}/plan", headers=headers)
    assert plan.status_code == 200
    assert plan.headers["content-type"].startswith("text/markdown")
    assert "## Deliverables" in plan.text
