"""Task CRUD, status board moves, project filter, and soft delete."""

from app.models.workspace import Task
from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


def test_task_round_trip(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    created = client.post(
        "/tasks",
        json={"title": "Draft the brief", "detail": "Outline the key points."},
        headers=BEARER,
    )
    assert created.status_code == 201
    task = created.json()
    assert task["title"] == "Draft the brief"
    assert task["detail"] == "Outline the key points."
    assert task["status"] == "todo"
    assert task["source"] == "manual"
    assert task["run_id"] is None
    assert task["agent_active"] is False

    fetched = client.get(f"/tasks/{task['id']}", headers=BEARER).json()
    assert fetched["title"] == "Draft the brief"

    # Move it across the Hermes board, then complete it.
    moved = client.patch(
        f"/tasks/{task['id']}", json={"status": "doing"}, headers=BEARER
    )
    assert moved.status_code == 200
    assert moved.json()["status"] == "doing"

    done = client.patch(f"/tasks/{task['id']}", json={"status": "done"}, headers=BEARER)
    assert done.json()["status"] == "done"

    listed = client.get("/tasks", headers=BEARER).json()
    assert any(t["id"] == task["id"] for t in listed)


def test_status_must_be_canonical(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    bad = client.post("/tasks", json={"title": "x", "status": "wip"}, headers=BEARER)
    assert bad.status_code == 400

    task_id = client.post("/tasks", json={"title": "ok"}, headers=BEARER).json()["id"]
    bad_patch = client.patch(f"/tasks/{task_id}", json={"status": "nope"}, headers=BEARER)
    assert bad_patch.status_code == 400


def test_project_filter(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    from app.models.project import Project

    project = Project(item_id=None, name="Inbox Tasks", slug="inbox-tasks-test", stage="idea")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    client.post(
        "/tasks", json={"title": "linked", "project_id": project.id}, headers=BEARER
    )
    client.post("/tasks", json={"title": "loose"}, headers=BEARER)

    scoped = client.get(
        "/tasks", params={"project_id": project.id}, headers=BEARER
    ).json()
    assert [t["title"] for t in scoped] == ["linked"]

    open_only = client.get("/tasks", params={"status": "todo"}, headers=BEARER).json()
    assert {t["title"] for t in open_only} == {"linked", "loose"}


def test_agent_active_surfaces_run_linked_task(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    from app.models.runtime import AgentRun
    from app.models.workspace import Task

    run = AgentRun(status="executing", kind="executor")
    db_session.add(run)
    db_session.flush()
    live = Task(user_id=seed_user.id, title="run linked", status="doing", source="run", run_id=run.id)
    idle = Task(user_id=seed_user.id, title="plain", status="doing", source="manual")
    db_session.add_all([live, idle])
    db_session.commit()

    by_title = {t["title"]: t for t in client.get("/tasks", headers=BEARER).json()}
    assert by_title["run linked"]["agent_active"] is True
    assert by_title["plain"]["agent_active"] is False


def test_detach_versus_unchanged_project(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    from app.models.project import Project

    project = Project(item_id=None, name="P", slug="p-detach-test", stage="idea")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    task_id = client.post(
        "/tasks", json={"title": "t", "project_id": project.id}, headers=BEARER
    ).json()["id"]

    # An omitted project_id leaves the link unchanged.
    unchanged = client.patch(f"/tasks/{task_id}", json={"detail": "edit"}, headers=BEARER)
    assert unchanged.json()["project_id"] == project.id

    # An explicit null detaches the task from its project.
    detached = client.patch(f"/tasks/{task_id}", json={"project_id": None}, headers=BEARER)
    assert detached.json()["project_id"] is None


def test_soft_delete_hides_but_keeps_recoverable(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    task_id = client.post("/tasks", json={"title": "to remove"}, headers=BEARER).json()["id"]

    deleted = client.delete(f"/tasks/{task_id}", headers=BEARER)
    assert deleted.status_code == 204

    assert all(t["id"] != task_id for t in client.get("/tasks", headers=BEARER).json())
    assert client.get(f"/tasks/{task_id}", headers=BEARER).status_code == 404

    row = db_session.get(Task, task_id)
    assert row is not None and row.deleted_at is not None
