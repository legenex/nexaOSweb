"""Download the project folder as a zip from the Process stage.

The Process stage writes the real project directory to NEXA_PROJECTS_ROOT/<slug>. The archive
endpoint streams that directory as a zip so the browser companion (which cannot reach the server
file system) can save a real local folder.
"""

import io
import zipfile

from app.models.inbox import InboxItem
from app.models.project import Project
from app.models.user import User
from app.safety import safe_write_text
from app.settings import get_settings

BEARER = {"Authorization": "Bearer t"}


def _bearer(monkeypatch):
    monkeypatch.setattr(get_settings(), "nexa_desktop_bearer", "t")


def _project(db_session, slug: str = "mailer"):
    """An item plus its project, owned by the only (earliest) user the bearer acts as."""
    user = User(email="owner@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    item = InboxItem(user_id=user.id, name="Mailer", body="b", status="routed", stage_history=[])
    db_session.add(item)
    db_session.flush()
    project = Project(item_id=item.id, name="Mailer", slug=slug, stage="process", plan_json={})
    db_session.add(project)
    db_session.commit()
    return item, project


def test_archive_streams_zip_of_the_project_folder(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("NEXA_PROJECTS_ROOT", str(tmp_path / "projects"))
    get_settings.cache_clear()
    _bearer(monkeypatch)
    item, project = _project(db_session)

    settings = get_settings()
    safe_write_text(settings.nexa_projects_root, f"{project.slug}/project_plan.md", "# Plan\n")
    safe_write_text(settings.nexa_projects_root, f"{project.slug}/requirements.md", "# Reqs\n")

    res = client.get(f"/flow/items/{item.id}/archive", headers=BEARER)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    assert f'filename="nexa-{project.slug}.zip"' in res.headers["content-disposition"]

    # The zip carries the real files, nested under the project slug so it unzips as a directory.
    with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
        names = set(archive.namelist())
        assert names == {
            f"{project.slug}/project_plan.md",
            f"{project.slug}/requirements.md",
        }
        assert archive.read(f"{project.slug}/project_plan.md").decode() == "# Plan\n"


def test_archive_is_404_when_no_folder_yet(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("NEXA_PROJECTS_ROOT", str(tmp_path / "projects"))
    get_settings.cache_clear()
    _bearer(monkeypatch)
    item, _ = _project(db_session, slug="not-processed")

    # No Process run means no on disk folder, so the download is an honest 404.
    res = client.get(f"/flow/items/{item.id}/archive", headers=BEARER)
    assert res.status_code == 404
