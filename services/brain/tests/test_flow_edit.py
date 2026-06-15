"""Project edit recorded as an agent run, and create-project-from-research."""

from app.models.project import Project
from app.models.runtime import AgentRun, AgentStep
from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "nexa_desktop_bearer", "test-bearer")
    monkeypatch.setattr(settings, "nexa_projects_root", str(tmp_path))


def test_edit_project_records_a_verified_run(client, seed_user, db_session, monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    project = Project(
        item_id=None, name="Edit me", slug="edit-me", stage="idea",
        plan_json={"summary": "x"}, selected_integrations=[],
    )
    db_session.add(project)
    db_session.commit()

    resp = client.post(
        f"/projects/{project.id}/edit",
        json={
            "build_destination": "vercel nexa",
            "scope_note": "keep it small",
            "selected_integrations": ["github"],
        },
        headers=BEARER,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project"]["build_destination"] == "vercel nexa"
    assert body["project"]["selected_integrations"] == ["github"]
    assert body["run_id"] and body["build_log_entry_id"]

    # The plan was rewritten through the path safety gate.
    assert (tmp_path / "edit-me" / "project_plan.md").exists()

    # The edit is recorded as an agent run with a verified edit step.
    run = db_session.get(AgentRun, body["run_id"])
    assert run.kind == "project_edit"
    steps = db_session.query(AgentStep).filter(AgentStep.run_id == run.id).all()
    assert any(s.kind == "edit" and s.status == "completed_verified" for s in steps)


def test_edit_requires_a_change(client, seed_user, db_session, monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    project = Project(item_id=None, name="No change", slug="no-change", stage="idea")
    db_session.add(project)
    db_session.commit()
    resp = client.post(f"/projects/{project.id}/edit", json={}, headers=BEARER)
    assert resp.status_code == 400


def test_create_project_from_research(client, seed_user, db_session, monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    research = Project(item_id=None, name="Solar research", slug="solar-research", stage="idea")
    db_session.add(research)
    db_session.commit()

    resp = client.post(
        f"/research/{research.id}/create-project",
        json={"name": "Solar build", "mode": "website"},
        headers=BEARER,
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["name"] == "Solar build"
    assert created["mode"] == "website"

    db_session.refresh(research)
    assert research.research_target_id == created["id"]
