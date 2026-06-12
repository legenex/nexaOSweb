"""Human gate and execute promote handoff."""

from pathlib import Path

from app.models.inbox import InboxItem
from app.models.project import PMRun, Project
from app.models.user import User
from app.settings import get_settings


def _approved_project(db_session, tmp_path, *, stage="approved"):
    monkeypatch_root = str(tmp_path)
    settings = get_settings()
    settings.nexa_projects_root = monkeypatch_root

    user = User(email="g@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    item = InboxItem(user_id=user.id, name="Launch", body="b", status="routed", stage_history=[])
    db_session.add(item)
    db_session.flush()

    slug = "launch"
    plan_dir = tmp_path / slug
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "project_plan.md").write_text("# Launch\n\n## Summary\nDo it\n")

    project = Project(
        item_id=item.id, name="Launch", slug=slug, stage=stage,
        plan_path=str(plan_dir / "project_plan.md"), plan_json={"summary": "Do it"},
    )
    db_session.add(project)
    db_session.commit()
    return item, user, project


def test_list_and_gate(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    item, _, project = _approved_project(db_session, tmp_path, stage="clarify")
    headers = {"Authorization": "Bearer t"}

    listed = client.get("/projects", headers=headers)
    assert listed.status_code == 200
    assert any(p["id"] == project.id for p in listed.json())

    approved = client.post(f"/projects/{project.id}/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["stage"] == "approved"

    rejected = client.post(
        f"/projects/{project.id}/reject", json={"reason": "scope too big"}, headers=headers
    )
    assert rejected.status_code == 200
    assert rejected.json()["stage"] == "rejected"


def test_promote_requires_approval(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    item, _, _ = _approved_project(db_session, tmp_path, stage="clarify")
    headers = {"Authorization": "Bearer t"}
    blocked = client.post(f"/flow/items/{item.id}/promote", headers=headers)
    assert blocked.status_code == 409


def test_promote_writes_requirements_and_pm_stub(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    item, _, project = _approved_project(db_session, tmp_path, stage="approved")
    headers = {"Authorization": "Bearer t"}

    promoted = client.post(f"/flow/items/{item.id}/promote", headers=headers)
    assert promoted.status_code == 200
    body = promoted.json()
    assert body["stage"] == "build"
    assert Path(body["requirements_path"]).name == "requirements.md"
    assert (tmp_path / "launch" / "requirements.md").exists()
    assert db_session.query(PMRun).filter(PMRun.project_id == project.id).count() == 1


def test_builder_guard_blocks_force_push():
    from app.agents.builder import BuilderError, _guard_commands

    import pytest

    with pytest.raises(BuilderError):
        _guard_commands(["git push --force origin main"])
    with pytest.raises(BuilderError):
        _guard_commands(["rm -rf /"])
