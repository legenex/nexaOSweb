"""Research project CRUD, generate-config, and run analysis fields."""

from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


def _create(client, **over):
    body = {"name": "Solar market scan", "topic": "residential solar", **over}
    return client.post("/research/projects", json=body, headers=BEARER)


def test_create_list_and_read(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    created = _create(client, depth="deep", goals=["sizing", "incentives"])
    assert created.status_code == 201
    body = created.json()
    assert body["topic"] == "residential solar"
    assert body["depth"] == "deep"
    assert body["goals"] == ["sizing", "incentives"]
    assert body["category"] == "general"

    listed = client.get("/research/projects", headers=BEARER).json()
    assert any(p["id"] == body["id"] for p in listed)


def test_update_and_recategorize(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)
    pid = _create(client).json()["id"]
    patched = client.patch(
        f"/research/projects/{pid}",
        json={"category": "market", "name": "Renamed scan", "depth": "quick"},
        headers=BEARER,
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["category"] == "market"
    assert body["name"] == "Renamed scan"
    assert body["depth"] == "quick"


def test_duplicate_and_delete(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    pid = _create(client).json()["id"]
    dup = client.post(f"/research/projects/{pid}/duplicate", headers=BEARER)
    assert dup.status_code == 201
    assert dup.json()["name"].endswith("(copy)")
    assert dup.json()["id"] != pid

    deleted = client.delete(f"/research/projects/{pid}", headers=BEARER)
    assert deleted.status_code == 204
    # Delete is soft: the project drops out of the list and its operations 404,
    assert all(p["id"] != pid for p in client.get("/research/projects", headers=BEARER).json())
    assert client.get(f"/research/projects/{pid}/findings", headers=BEARER).status_code == 404
    # but the row is preserved and flagged, so the project stays recoverable.
    from app.models.project import Project

    row = db_session.get(Project, pid)
    assert row is not None
    assert row.research_config.get("deleted") is True


def test_generate_config(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)

    def fake_synth(key, prompt, schema, **_):
        assert key == "research_synthesis"
        return {
            "purpose": "Understand the residential solar market.",
            "goals": ["map competitors", "size demand"],
            "depth": "deep",
            "lookback": 90,
            "schedule": "weekly",
        }

    monkeypatch.setattr("app.agents.research.synthesize_json", fake_synth)
    response = client.post(
        "/research/generate-config",
        json={"topic": "residential solar", "name": "Solar scan"},
        headers=BEARER,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["depth"] == "deep"
    assert body["schedule"] == "weekly"
    assert body["lookback"] == 90
    assert len(body["goals"]) == 2


def test_run_carries_analysis_and_suggestions(client, seed_user, monkeypatch):
    _enable_bearer(monkeypatch)

    def fake_synth(key, prompt, schema, **_):
        return {
            "summary": "Two findings.",
            "analysis": "The market is fragmented and price sensitive.",
            "key_takeaways": ["fragmented", "price sensitive"],
            "suggestions": ["target installers"],
            "findings": [{"title": "A", "detail": "a"}, {"title": "B", "detail": "b"}],
        }

    monkeypatch.setattr("app.agents.research.synthesize_json", fake_synth)
    pid = _create(client).json()["id"]
    run = client.post(f"/research/{pid}/runs", headers=BEARER)
    assert run.status_code == 201
    body = run.json()
    assert body["analysis"].startswith("The market")
    assert body["key_takeaways"] == ["fragmented", "price sensitive"]
    assert body["suggestions"] == ["target installers"]
    assert body["findings_count"] == 2


def test_generate_is_honest_without_a_model(client, seed_user, monkeypatch):
    # No provider key and no injected model: generate must fail clearly, not return stubs.
    _enable_bearer(monkeypatch)
    response = client.post(
        "/research/generate-config",
        json={"topic": "residential solar", "name": "Solar scan"},
        headers=BEARER,
    )
    assert response.status_code == 503


def test_run_is_honest_without_a_model(client, seed_user, monkeypatch):
    # A run with no model fails and writes no placeholder findings.
    _enable_bearer(monkeypatch)
    pid = _create(client).json()["id"]
    run = client.post(f"/research/{pid}/runs", headers=BEARER)
    assert run.status_code == 503
    findings = client.get(f"/research/{pid}/findings", headers=BEARER).json()
    assert findings == []
