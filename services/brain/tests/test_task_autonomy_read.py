"""The per task autonomy read projection on TaskRead.

The web AutonomySelector needs the task's real stored level on reopen, not the project default. These
tests prove TaskRead now projects the stored autonomy column: a freshly created task reports its
inherited level, and a per task override set through the AB4.3 endpoint round-trips through both GET
task and the build task graph.
"""

from app.models.project import Project
from app.models.user import User
from app.models.workspace import Task


def _bearer(monkeypatch):
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")
    return {"Authorization": "Bearer t"}


def _user(db):
    user = User(email="reader@example.com", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _project(db, **kwargs):
    project = Project(name="Read App", slug="read-app", stage="approved", mode="app", **kwargs)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _task(db, user, project, *, autonomy="yellow"):
    task = Task(
        user_id=user.id,
        project_id=project.id,
        title="A task",
        status="todo",
        source="manual",
        autonomy=autonomy,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_task_read_projects_the_stored_autonomy(client, db_session, monkeypatch):
    headers = _bearer(monkeypatch)
    user = _user(db_session)
    project = _project(db_session)
    task = _task(db_session, user, project, autonomy="red")

    res = client.get(f"/tasks/{task.id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["autonomy"] == "red"


def test_per_task_override_round_trips_through_task_read(client, db_session, monkeypatch):
    headers = _bearer(monkeypatch)
    user = _user(db_session)
    project = _project(db_session)
    task = _task(db_session, user, project, autonomy="green")

    # A fresh task reports its set level.
    assert client.get(f"/tasks/{task.id}", headers=headers).json()["autonomy"] == "green"

    # Override it through the AB4.3 endpoint.
    put = client.put(
        f"/agents/tasks/{task.id}/autonomy", json={"level": "red"}, headers=headers
    )
    assert put.status_code == 200
    assert put.json()["level"] == "red"

    # The override is visible on reopen through TaskRead, not just the autonomy endpoint.
    assert client.get(f"/tasks/{task.id}", headers=headers).json()["autonomy"] == "red"

    # And in the list projection.
    listed = client.get("/tasks", headers=headers).json()
    mine = next(t for t in listed if t["id"] == task.id)
    assert mine["autonomy"] == "red"
