"""A project mode chosen at capture rides through to the created project."""

from app.agents.route import get_or_create_project_for_item
from app.models.inbox import InboxItem
from app.project_modes import destination_for
from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


def test_capture_stashes_a_valid_mode(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    response = client.post(
        "/intake/capture",
        data={"name": "A marketing site", "mode": "website"},
        headers=BEARER,
    )
    assert response.status_code == 201
    assert response.json()["stage_history"][0]["mode"] == "website"


def test_capture_ignores_an_unknown_mode(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    response = client.post(
        "/intake/capture",
        data={"name": "Mystery", "mode": "nonsense"},
        headers=BEARER,
    )
    assert response.status_code == 201
    assert "mode" not in response.json()["stage_history"][0]


def test_project_creation_applies_the_captured_mode(db_session, seed_user):
    item = InboxItem(
        user_id=seed_user.id,
        name="Build a funnel",
        body="",
        source="note",
        status="captured",
        stage_history=[{"stage": "capture", "mode": "funnel", "state": "done"}],
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    project = get_or_create_project_for_item(db_session, item)
    db_session.commit()

    assert project.mode == "funnel"
    assert project.build_destination == destination_for("funnel")
