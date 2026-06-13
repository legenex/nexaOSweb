"""Execute handoff to the builder.

Promotes an approved project by converting its plan into requirements.md, the source of
truth, then handing off to the builder. Every write goes through the path safety gate.
The builder never runs a dangerous command and never force pushes a protected branch.

The full project manager agent and the specialist sub agents are deferred to a dedicated
later milestone. This stage only writes requirements and records a PMRun stub.
"""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.inbox import InboxItem, PipelineRun
from app.models.project import BuildLogEntry, PMRun, Project
from app.safety import PROTECTED_BRANCHES, ensure_within_root, is_dangerous, safe_write_text
from app.settings import get_settings

logger = logging.getLogger(__name__)


class BuilderError(Exception):
    """Raised when a project cannot be promoted or a guard refuses a command."""


def _guard_commands(commands: list[str]) -> None:
    for command in commands:
        if is_dangerous(command):
            raise BuilderError(f"refused dangerous command: {command}")
        lowered = command.lower()
        if "push" in lowered and "--force" in lowered:
            for branch in PROTECTED_BRANCHES:
                if branch in lowered:
                    raise BuilderError(f"refused force push to protected branch: {branch}")


def promote_project(db: Session, item: InboxItem, project: Project) -> tuple[Project, PMRun, str]:
    settings = get_settings()
    if not project.plan_path:
        raise BuilderError("project has no plan to promote")

    plan_md = ensure_within_root(settings.nexa_projects_root, project.plan_path).read_text(
        encoding="utf-8"
    )
    requirements = (
        "# Requirements\n\n"
        "This file is the source of truth for the build. It is generated from the "
        "approved plan and supersedes the draft plan.\n\n"
        f"{plan_md}"
    )
    written = safe_write_text(
        settings.nexa_projects_root, Path(project.slug) / "requirements.md", requirements
    )

    # Representative builder commands, guarded before any execution would occur.
    build_commands = [
        f"git checkout -b build/{project.slug}",
        "git add requirements.md",
        "git commit -m 'scaffold from requirements'",
    ]
    _guard_commands(build_commands)

    pm = PMRun(project_id=project.id, status="active")
    db.add(pm)
    db.add(
        BuildLogEntry(
            project_id=project.id,
            action="build",
            status="applied",
            summary="Promoted from approved plan, wrote requirements.md",
            file_path="requirements.md",
            diff_summary=(
                "Generated requirements.md for build destination "
                f"{project.build_destination}"
            ),
            before_content=None,
            after_content=requirements,
        )
    )
    project.stage = "build"
    item.status = "executing"
    item.stage_history = [*item.stage_history, {"stage": "execute", "state": "handed_off"}]
    db.add(PipelineRun(item_id=item.id, stage="execute", state="done", finished_at=utcnow()))
    db.commit()
    db.refresh(project)
    db.refresh(pm)
    return project, pm, str(written)
