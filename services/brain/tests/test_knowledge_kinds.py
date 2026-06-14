"""The personal memory kinds: rejected_approach and recurring_correction are first-class."""

from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


def test_new_kinds_can_be_created_and_listed(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    for kind in ("rejected_approach", "recurring_correction"):
        created = client.post(
            "/knowledge",
            json={
                "kind": kind,
                "scope": "development",
                "source": "manual",
                "content": f"a {kind} the agent should remember",
                "confidence": 0.7,
            },
            headers=BEARER,
        )
        assert created.status_code == 201
        assert created.json()["kind"] == kind

    listed = client.get("/knowledge?scope=development", headers=BEARER).json()
    kinds = {entry["kind"] for entry in listed}
    assert {"rejected_approach", "recurring_correction"} <= kinds


def test_new_kind_is_editable(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    created = client.post(
        "/knowledge",
        json={"kind": "fact", "scope": "development", "content": "x"},
        headers=BEARER,
    ).json()
    patched = client.patch(
        f"/knowledge/{created['id']}",
        json={"kind": "recurring_correction"},
        headers=BEARER,
    )
    assert patched.status_code == 200
    assert patched.json()["kind"] == "recurring_correction"


def test_unknown_kind_is_still_rejected(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    response = client.post(
        "/knowledge",
        json={"kind": "nonsense", "scope": "development", "content": "x"},
        headers=BEARER,
    )
    assert response.status_code == 422
