"""Research to project attachment, run writes, and finding level actions."""

from app.models.project import Project
from app.settings import get_settings

BEARER = {"Authorization": "Bearer test-bearer"}


def _enable_bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "test-bearer")


def _fake_synth(key, prompt, schema):
    # Deterministic findings so the run is independent of any provider.
    return {
        "summary": "Two grounded findings about the build.",
        "findings": [
            {
                "title": "Competitors price weekly",
                "detail": "Three of five charge per week.",
                "url": "https://example.com/a",
            },
            {
                "title": "Readers prefer short",
                "detail": "Engagement rises with shorter posts.",
                "url": None,
            },
        ],
    }


def _make_projects(db, user):
    build = Project(name="Build the newsletter", slug="build-newsletter", stage="approved")
    research = Project(name="Newsletter research", slug="newsletter-research", stage="idea")
    db.add(build)
    db.add(research)
    db.commit()
    db.refresh(build)
    db.refresh(research)
    return build, research


def test_attach_and_detach(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    build, research = _make_projects(db_session, seed_user)

    attached = client.post(
        f"/research/{research.id}/attach",
        json={"target_project_id": build.id},
        headers=BEARER,
    )
    assert attached.status_code == 200
    assert attached.json()["research_target_id"] == build.id

    detached = client.post(f"/research/{research.id}/detach", headers=BEARER)
    assert detached.status_code == 200
    assert detached.json()["research_target_id"] is None


def test_attach_rejects_self_and_missing_target(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    _build, research = _make_projects(db_session, seed_user)

    same = client.post(
        f"/research/{research.id}/attach",
        json={"target_project_id": research.id},
        headers=BEARER,
    )
    assert same.status_code == 400

    missing = client.post(
        f"/research/{research.id}/attach",
        json={"target_project_id": 999999},
        headers=BEARER,
    )
    assert missing.status_code == 404


def test_run_writes_findings_into_target_update_log(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    monkeypatch.setattr("app.agents.research.synthesize_json", _fake_synth)
    build, research = _make_projects(db_session, seed_user)
    client.post(
        f"/research/{research.id}/attach",
        json={"target_project_id": build.id},
        headers=BEARER,
    )

    run = client.post(f"/research/{research.id}/runs", headers=BEARER)
    assert run.status_code == 201
    body = run.json()
    assert body["status"] == "completed"
    assert body["findings_count"] == 2
    assert len(body["findings"]) == 2

    # The build project's Update Log now carries the findings.
    updates = client.get(f"/projects/{build.id}/updates", headers=BEARER).json()
    assert len(updates) == 2
    assert all(u["kind"] == "research_finding" for u in updates)
    titles = {u["title"] for u in updates}
    assert "Competitors price weekly" in titles


def test_run_without_attachment_creates_findings_but_no_updates(
    client, seed_user, db_session, monkeypatch
):
    _enable_bearer(monkeypatch)
    monkeypatch.setattr("app.agents.research.synthesize_json", _fake_synth)
    build, research = _make_projects(db_session, seed_user)

    run = client.post(f"/research/{research.id}/runs", headers=BEARER)
    assert run.json()["findings_count"] == 2
    # Nothing posted to the unrelated build project.
    assert client.get(f"/projects/{build.id}/updates", headers=BEARER).json() == []


def test_finding_actions(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    monkeypatch.setattr("app.agents.research.synthesize_json", _fake_synth)
    build, research = _make_projects(db_session, seed_user)
    client.post(
        f"/research/{research.id}/attach",
        json={"target_project_id": build.id},
        headers=BEARER,
    )
    client.post(f"/research/{research.id}/runs", headers=BEARER)
    findings = client.get(f"/research/{research.id}/findings", headers=BEARER).json()
    assert len(findings) == 2
    a, b, c = findings[0]["id"], findings[1]["id"], findings[0]["id"]

    # to-task
    task = client.post(f"/research/findings/{a}/to-task", headers=BEARER)
    assert task.status_code == 201
    assert task.json()["project_id"] == build.id
    assert task.json()["title"]

    # to-knowledge
    knowledge = client.post(f"/research/findings/{b}/to-knowledge", headers=BEARER)
    assert knowledge.status_code == 201
    assert knowledge.json()["source"] == "connector"
    assert knowledge.json()["provenance"]["from"] == "research_finding"

    # to-update lands another entry in the build project's log
    before = len(client.get(f"/projects/{build.id}/updates", headers=BEARER).json())
    update = client.post(f"/research/findings/{c}/to-update", headers=BEARER)
    assert update.status_code == 201
    assert update.json()["project_id"] == build.id
    after = len(client.get(f"/projects/{build.id}/updates", headers=BEARER).json())
    assert after == before + 1


def test_to_update_requires_attachment(client, seed_user, db_session, monkeypatch):
    _enable_bearer(monkeypatch)
    monkeypatch.setattr("app.agents.research.synthesize_json", _fake_synth)
    _build, research = _make_projects(db_session, seed_user)
    client.post(f"/research/{research.id}/runs", headers=BEARER)
    finding_id = client.get(f"/research/{research.id}/findings", headers=BEARER).json()[0]["id"]

    conflict = client.post(f"/research/findings/{finding_id}/to-update", headers=BEARER)
    assert conflict.status_code == 409
