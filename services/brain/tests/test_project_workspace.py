"""Project modes and the Projects workspace endpoints."""

import app.agents.project_editor as editor_mod
from app.models.inbox import InboxItem
from app.models.project import BuildLogEntry, Integration, Project
from app.models.user import User
from app.project_modes import capture_questions_for, destination_for
from app.settings import get_settings

BEARER = {"Authorization": "Bearer t"}


def _setup(db_session, tmp_path, monkeypatch, *, slug="app-one", mode="app"):
    monkeypatch.setattr(get_settings(), "nexa_projects_root", str(tmp_path))
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    user = User(email="w@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    item = InboxItem(user_id=user.id, name="App One", body="b", status="routed", stage_history=[])
    db_session.add(item)
    db_session.flush()
    project = Project(
        item_id=item.id,
        name="App One",
        slug=slug,
        stage="process",
        mode=mode,
        plan_json={"recommended_next_steps": ["Ship the MVP"]},
        selected_integrations=["stripe", "mailchimp"],
    )
    db_session.add(project)
    db_session.add(Integration(user_id=user.id, provider="stripe", status="connected"))
    db_session.commit()
    db_session.refresh(project)
    # Seed an on disk file in the project folder.
    folder = tmp_path / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "project_plan.md").write_text("# App One\n\nDraft.\n", encoding="utf-8")
    return item, user, project


def test_list_modes(client, db_session, tmp_path, monkeypatch):
    _setup(db_session, tmp_path, monkeypatch)
    res = client.get("/projects/modes", headers=BEARER)
    assert res.status_code == 200
    keys = {m["key"] for m in res.json()}
    assert {"app", "automation", "website", "funnel", "data_pipeline", "campaign",
            "content_system", "product_concept"} <= keys


def test_set_mode_persists_and_changes_destination(client, db_session, tmp_path, monkeypatch):
    _, _, project = _setup(db_session, tmp_path, monkeypatch)
    res = client.post(f"/projects/{project.id}/mode", json={"mode": "website"}, headers=BEARER)
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "website"
    assert body["build_destination"] == destination_for("website")

    bad = client.post(f"/projects/{project.id}/mode", json={"mode": "nope"}, headers=BEARER)
    assert bad.status_code == 400


def test_mode_changes_capture_questions(client, db_session, tmp_path, monkeypatch):
    import app.agents.clarify as clarify_mod

    item, _, project = _setup(db_session, tmp_path, monkeypatch, mode="app")
    monkeypatch.setattr(
        clarify_mod, "synthesize_json", lambda key, prompt, schema=None: {"questions": []}
    )
    app_q = client.get(f"/flow/items/{item.id}/clarify", headers=BEARER).json()
    assert app_q["clarifying_questions"] == capture_questions_for("app")

    client.post(f"/projects/{project.id}/mode", json={"mode": "funnel"}, headers=BEARER)
    funnel_q = client.get(f"/flow/items/{item.id}/clarify", headers=BEARER).json()
    assert funnel_q["clarifying_questions"] == capture_questions_for("funnel")
    assert app_q["clarifying_questions"] != funnel_q["clarifying_questions"]


def test_overview_returns_real_data(client, db_session, tmp_path, monkeypatch):
    _, _, project = _setup(db_session, tmp_path, monkeypatch)
    res = client.get(f"/projects/{project.id}/overview", headers=BEARER)
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "App One"
    assert body["type"] == "app"
    assert body["stage"] == "process"
    assert body["next_recommended_action"] == "Ship the MVP"
    providers = {i["provider"]: i for i in body["connected_integrations"]}
    assert providers["stripe"]["status"] == "connected"
    assert providers["mailchimp"]["status"] == "available"

    patched = client.patch(
        f"/projects/{project.id}/overview",
        json={"current_blocker": "waiting on API key", "priority": "high"},
        headers=BEARER,
    )
    assert patched.status_code == 200
    assert patched.json()["current_blocker"] == "waiting on API key"
    assert patched.json()["priority"] == "high"


def test_files_tree_and_content_with_path_safety(client, db_session, tmp_path, monkeypatch):
    _, _, project = _setup(db_session, tmp_path, monkeypatch)
    files = client.get(f"/projects/{project.id}/files", headers=BEARER).json()
    paths = {n["path"] for n in files["tree"]}
    assert "project_plan.md" in paths
    required = {r["path"]: r["present"] for r in files["required_files"]}
    assert required["project_plan.md"] is True
    assert required["requirements.md"] is False

    content = client.get(
        f"/projects/{project.id}/files/content", params={"path": "project_plan.md"}, headers=BEARER
    )
    assert content.status_code == 200
    assert "App One" in content.json()["content"]

    escape = client.get(
        f"/projects/{project.id}/files/content", params={"path": "../../etc/passwd"}, headers=BEARER
    )
    assert escape.status_code == 400


def test_editor_gate_propose_apply_rollback(client, db_session, tmp_path, monkeypatch):
    _, _, project = _setup(db_session, tmp_path, monkeypatch)
    monkeypatch.setattr(
        editor_mod,
        "synthesize_json",
        lambda key, prompt, schema=None: {
            "new_content": "# App One\n\nUpdated body.\n",
            "change_summary": "Rewrite the body",
        },
    )

    # Propose writes nothing to disk and creates no build log entry yet.
    proposed = client.post(
        f"/projects/{project.id}/editor/propose",
        json={"file_path": "project_plan.md", "instruction": "rewrite the body"},
        headers=BEARER,
    )
    assert proposed.status_code == 200
    proposal = proposed.json()
    assert "addition" in proposal["diff_summary"]
    assert "Updated body" in proposal["after_content"]
    assert (tmp_path / "app-one" / "project_plan.md").read_text() == "# App One\n\nDraft.\n"
    assert client.get(f"/projects/{project.id}/build-log", headers=BEARER).json() == []

    # Apply without approval is refused by the gate.
    refused = client.post(
        f"/projects/{project.id}/editor/apply",
        json={"proposal_id": proposal["proposal_id"], "approved": False},
        headers=BEARER,
    )
    assert refused.status_code == 403
    assert (tmp_path / "app-one" / "project_plan.md").read_text() == "# App One\n\nDraft.\n"

    # Approved apply writes the file and records a build log entry.
    applied = client.post(
        f"/projects/{project.id}/editor/apply",
        json={"proposal_id": proposal["proposal_id"], "approved": True},
        headers=BEARER,
    )
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert (tmp_path / "app-one" / "project_plan.md").read_text() == "# App One\n\nUpdated body.\n"
    log = client.get(f"/projects/{project.id}/build-log", headers=BEARER).json()
    assert len(log) == 1
    assert log[0]["action"] == "edit"

    # Rollback restores the prior content and logs a rollback entry.
    rolled = client.post(
        f"/projects/{project.id}/editor/rollback",
        json={"build_log_id": proposal["proposal_id"]},
        headers=BEARER,
    )
    assert rolled.status_code == 200
    assert rolled.json()["status"] == "applied"
    assert (tmp_path / "app-one" / "project_plan.md").read_text() == "# App One\n\nDraft.\n"
    log_after = client.get(f"/projects/{project.id}/build-log", headers=BEARER).json()
    actions = [e["action"] for e in log_after]
    assert "rollback" in actions


def test_editor_rollback_of_new_file_removes_it(client, db_session, tmp_path, monkeypatch):
    _, _, project = _setup(db_session, tmp_path, monkeypatch)
    monkeypatch.setattr(
        editor_mod,
        "synthesize_json",
        lambda key, prompt, schema=None: {
            "new_content": "fresh\n",
            "change_summary": "create notes",
        },
    )
    proposal = client.post(
        f"/projects/{project.id}/editor/propose",
        json={"file_path": "notes.md", "instruction": "create notes"},
        headers=BEARER,
    ).json()
    assert proposal["before_content"] is None
    client.post(
        f"/projects/{project.id}/editor/apply",
        json={"proposal_id": proposal["proposal_id"], "approved": True},
        headers=BEARER,
    )
    assert (tmp_path / "app-one" / "notes.md").exists()
    client.post(
        f"/projects/{project.id}/editor/rollback",
        json={"build_log_id": proposal["proposal_id"]},
        headers=BEARER,
    )
    assert not (tmp_path / "app-one" / "notes.md").exists()


def test_rename_project_changes_name_keeps_slug(client, db_session, tmp_path, monkeypatch):
    _, _, project = _setup(db_session, tmp_path, monkeypatch)
    res = client.patch(f"/projects/{project.id}", json={"name": "Renamed App"}, headers=BEARER)
    assert res.status_code == 200
    assert res.json()["name"] == "Renamed App"
    assert res.json()["slug"] == "app-one"

    blank = client.patch(f"/projects/{project.id}", json={"name": "   "}, headers=BEARER)
    assert blank.status_code == 400


def test_duplicate_project_copies_row_and_files(client, db_session, tmp_path, monkeypatch):
    _, _, project = _setup(db_session, tmp_path, monkeypatch)
    res = client.post(f"/projects/{project.id}/duplicate", headers=BEARER)
    assert res.status_code == 201
    copy = res.json()
    assert copy["id"] != project.id
    assert copy["name"] == "App One (copy)"
    assert copy["slug"] != project.slug
    assert copy["stage"] == "idea"
    # The on disk folder was copied into the new slug folder.
    files = client.get(f"/projects/{copy['id']}/files", headers=BEARER).json()
    assert "project_plan.md" in {n["path"] for n in files["tree"]}
    # Both the original and the copy are listed.
    listed = {p["id"] for p in client.get("/projects", headers=BEARER).json()}
    assert {project.id, copy["id"]} <= listed


def test_soft_delete_hides_project_but_keeps_row(client, db_session, tmp_path, monkeypatch):
    _, _, project = _setup(db_session, tmp_path, monkeypatch)
    res = client.delete(f"/projects/{project.id}", headers=BEARER)
    assert res.status_code == 204
    # Gone from the list and no longer loadable, but the row survives for recovery.
    listed = {p["id"] for p in client.get("/projects", headers=BEARER).json()}
    assert project.id not in listed
    assert client.get(f"/projects/{project.id}/overview", headers=BEARER).status_code == 404
    db_session.expire_all()
    assert db_session.get(Project, project.id) is not None


def test_delete_file_removes_it_and_logs(client, db_session, tmp_path, monkeypatch):
    _, _, project = _setup(db_session, tmp_path, monkeypatch)
    res = client.delete(
        f"/projects/{project.id}/files", params={"path": "project_plan.md"}, headers=BEARER
    )
    assert res.status_code == 200
    assert res.json()["deleted"] is True
    assert not (tmp_path / "app-one" / "project_plan.md").exists()
    log = client.get(f"/projects/{project.id}/build-log", headers=BEARER).json()
    assert any(e["action"] == "delete" and e["file_path"] == "project_plan.md" for e in log)

    missing = client.delete(
        f"/projects/{project.id}/files", params={"path": "project_plan.md"}, headers=BEARER
    )
    assert missing.status_code == 404

    escape = client.delete(
        f"/projects/{project.id}/files", params={"path": "../../etc/passwd"}, headers=BEARER
    )
    assert escape.status_code == 400


def test_editor_propose_rejects_escaping_path(client, db_session, tmp_path, monkeypatch):
    _, _, project = _setup(db_session, tmp_path, monkeypatch)
    # No synthesize patch needed: the path gate fails before any model call.
    res = client.post(
        f"/projects/{project.id}/editor/propose",
        json={"file_path": "../escape.md", "instruction": "x"},
        headers=BEARER,
    )
    assert res.status_code == 400
    assert db_session.query(BuildLogEntry).count() == 0
