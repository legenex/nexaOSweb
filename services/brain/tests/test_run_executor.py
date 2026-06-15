"""The watched executor entrypoint: a real run that parks at the human gate, nothing merged."""

from pathlib import Path

from app.models.project import Project
from app.models.runtime import AgentStep
from app.runtime import WAITING_APPROVAL
from app.settings import get_settings
from scripts.run_executor import run_executor


def test_run_executor_produces_a_run_parked_at_the_gate(db_session, monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "nexa_projects_root", str(tmp_path / "projects"))
    monkeypatch.setattr(settings, "nexa_runtime_root", str(tmp_path / "runtime"))

    slug = "exec-demo"
    reqs_dir = Path(tmp_path) / "projects" / slug
    reqs_dir.mkdir(parents=True)
    (reqs_dir / "requirements.md").write_text(
        "# Requirements\n\n- Build the landing page\n- Add tracking\n", encoding="utf-8"
    )
    project = Project(item_id=None, name="Exec demo", slug=slug, stage="approved", plan_json={})
    db_session.add(project)
    db_session.commit()

    # checks=[] keeps the test fast; the script uses the mode checks by default.
    result = run_executor(db_session, project.id, checks=[])

    assert result["run_id"] is not None
    # The run parks at the human gate and is never merged.
    assert result["status"] == WAITING_APPROVAL

    steps = (
        db_session.query(AgentStep)
        .filter(AgentStep.run_id == result["run_id"])
        .all()
    )
    kinds = {s.kind for s in steps}
    # Real edit steps were produced, and an approval request holds the run.
    assert "edit" in kinds
    assert any(s.kind == "approval_request" and s.status == WAITING_APPROVAL for s in steps)
    # No merge step exists: nothing left the worktree.
    assert "merge" not in kinds
