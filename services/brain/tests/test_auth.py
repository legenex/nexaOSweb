"""Auth acceptance: login sets the cookie, bearer authenticates, CSRF is enforced."""

from fastapi import Depends

from app.main import app
from app.security.auth import CSRF_COOKIE, SESSION_COOKIE, Principal, get_principal
from app.settings import get_settings


# A protected, state changing probe route used only by these tests.
@app.post("/_test/protected")
def _protected(principal: Principal = Depends(get_principal)) -> dict[str, str]:
    return {"kind": principal.kind}


def test_login_sets_session_cookie(client, seed_user):
    response = client.post(
        "/auth/login",
        json={"email": "nick@example.com", "password": "correct horse"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "nick@example.com"
    assert body["csrf_token"]
    assert SESSION_COOKIE in response.cookies
    assert CSRF_COOKIE in response.cookies


def test_login_rejects_bad_password(client, seed_user):
    response = client.post(
        "/auth/login",
        json={"email": "nick@example.com", "password": "wrong"},
    )
    assert response.status_code == 401
    assert SESSION_COOKIE not in response.cookies


def test_bearer_request_authenticates(client, seed_user):
    settings = get_settings()
    original = settings.nexa_desktop_bearer
    settings.nexa_desktop_bearer = "desktop-secret-token"
    try:
        response = client.post(
            "/_test/protected",
            headers={"Authorization": "Bearer desktop-secret-token"},
        )
        assert response.status_code == 200
        assert response.json()["kind"] == "bearer"
    finally:
        settings.nexa_desktop_bearer = original


def test_state_change_without_csrf_is_rejected(client, seed_user):
    login = client.post(
        "/auth/login",
        json={"email": "nick@example.com", "password": "correct horse"},
    )
    assert login.status_code == 200
    blocked = client.post("/_test/protected")
    assert blocked.status_code == 403


def test_state_change_with_matching_csrf_is_allowed(client, seed_user):
    login = client.post(
        "/auth/login",
        json={"email": "nick@example.com", "password": "correct horse"},
    )
    csrf = login.json()["csrf_token"]
    allowed = client.post("/_test/protected", headers={"X-CSRF-Token": csrf})
    assert allowed.status_code == 200
    assert allowed.json()["kind"] == "session"
