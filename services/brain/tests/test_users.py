"""User management: list, invite, change role, remove, and self profile."""

from app.models.user import User
from app.settings import get_settings

BEARER = {"Authorization": "Bearer t"}


def _bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")


def test_list_and_invite(client, seed_user, db_session, monkeypatch):
    _bearer(monkeypatch)
    listed = client.get("/users", headers=BEARER)
    assert listed.status_code == 200
    assert any(u["id"] == seed_user.id for u in listed.json())

    invited = client.post(
        "/users/invite",
        json={"email": "new@example.com", "name": "New Person", "role": "member"},
        headers=BEARER,
    )
    assert invited.status_code == 201
    body = invited.json()
    assert body["status"] == "invited"
    assert body["role"] == "member"

    # Duplicate email is a conflict.
    dup = client.post("/users/invite", json={"email": "new@example.com"}, headers=BEARER)
    assert dup.status_code == 409


def test_change_role_and_remove(client, seed_user, db_session, monkeypatch):
    _bearer(monkeypatch)
    invited = client.post(
        "/users/invite", json={"email": "teammate@example.com"}, headers=BEARER
    ).json()

    promoted = client.patch(
        f"/users/{invited['id']}", json={"role": "admin"}, headers=BEARER
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    removed = client.delete(f"/users/{invited['id']}", headers=BEARER)
    assert removed.status_code == 200
    assert removed.json()["status"] == "removed"

    # Soft removed users drop out of the list.
    ids = {u["id"] for u in client.get("/users", headers=BEARER).json()}
    assert invited["id"] not in ids


def test_cannot_remove_self(client, seed_user, db_session, monkeypatch):
    _bearer(monkeypatch)
    # The bearer acts as the earliest user, which is seed_user.
    blocked = client.delete(f"/users/{seed_user.id}", headers=BEARER)
    assert blocked.status_code == 409


def test_profile_update(client, seed_user, db_session, monkeypatch):
    _bearer(monkeypatch)
    res = client.patch("/auth/me", json={"name": "Renamed"}, headers=BEARER)
    assert res.status_code == 200
    assert res.json()["name"] == "Renamed"
    assert db_session.get(User, seed_user.id).name == "Renamed"
