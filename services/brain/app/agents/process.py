"""Process stage.

Turns a project shaped item into a project folder and a draft plan. It reuses the
Project the router created, generates a structured plan via synthesize_json, renders it
to project_plan.md inside NEXA_PROJECTS_ROOT through the path safety gate, and persists
plan_path, plan_json, and build_destination. It does not activate the project.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.agents.route import _latest_record
from app.json_extract import synthesize_json
from app.models.base import utcnow
from app.models.inbox import InboxItem, PipelineRun
from app.models.project import Project
from app.safety import ensure_within_root, safe_write_text
from app.settings import get_settings
from app.util import slugify

logger = logging.getLogger(__name__)

PLAN_SECTIONS = [
    ("summary", "Summary"),
    ("objective", "Objective"),
    ("recommended_outcome", "Recommended outcome"),
    ("project_tree", "Project tree"),
    ("workstreams", "Workstreams"),
    ("deliverables", "Deliverables"),
    ("subtasks", "Subtasks"),
    ("dependencies", "Dependencies"),
    ("assets", "Assets"),
    ("owners", "Owners"),
    ("open_questions", "Open questions"),
    ("risks", "Risks"),
    ("estimated_complexity", "Estimated complexity"),
    ("recommended_next_steps", "Recommended next steps"),
    ("proposed_build_destination", "Proposed build destination"),
    ("likely_integrations", "Likely integrations"),
]

_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "objective": {"type": "string"},
        "recommended_outcome": {"type": "string"},
        "project_tree": {"type": "array", "items": {"type": "string"}},
        "workstreams": {"type": "array", "items": {"type": "string"}},
        "deliverables": {"type": "array", "items": {"type": "string"}},
        "subtasks": {"type": "array", "items": {"type": "string"}},
        "dependencies": {"type": "array", "items": {"type": "string"}},
        "assets": {"type": "array", "items": {"type": "string"}},
        "owners": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "estimated_complexity": {"type": "string"},
        "recommended_next_steps": {"type": "array", "items": {"type": "string"}},
        "proposed_build_destination": {"type": "string"},
        "likely_integrations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "objective", "proposed_build_destination", "likely_integrations"],
}


class ProcessError(Exception):
    """Raised when an item cannot be processed (not project shaped)."""


def _plan_prompt(item: InboxItem, tags: list[str]) -> str:
    return (
        "Produce a structured implementation plan for this project as JSON.\n\n"
        f"Name: {item.name}\n"
        f"Description: {item.body}\n"
        f"Tags: {', '.join(tags) if tags else 'none'}\n\n"
        "Include summary, objective, recommended_outcome, project_tree, workstreams, "
        "deliverables, subtasks, dependencies, assets, owners, open_questions, risks, "
        "estimated_complexity, recommended_next_steps, proposed_build_destination, and "
        "likely_integrations. Keep lists concrete and US market oriented."
    )


def render_plan_markdown(name: str, plan: dict[str, Any]) -> str:
    lines = [f"# {name}", "", "Draft plan. Not yet activated.", ""]
    for key, heading in PLAN_SECTIONS:
        value = plan.get(key)
        if value in (None, "", [], {}):
            continue
        lines.append(f"## {heading}")
        if isinstance(value, list):
            lines.extend(f"- {entry}" for entry in value)
        else:
            lines.append(str(value))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def process_item(
    db: Session,
    item: InboxItem,
    *,
    synthesize: Callable[..., dict[str, Any]] | None = None,
) -> Project:
    synthesize = synthesize or synthesize_json
    record = _latest_record(db, item.id)

    project = db.query(Project).filter(Project.item_id == item.id).first()
    if project is None:
        if record is None or record.recommended_route != "project":
            raise ProcessError("item is not project shaped")
        project = Project(item_id=item.id, name=item.name, slug=slugify(item.name), stage="idea")
        db.add(project)
        db.flush()

    model_key = record.recommended_model_key if record else "agentic_code"
    tags = record.tags if record and isinstance(record.tags, list) else []
    plan = synthesize(model_key, _plan_prompt(item, tags), _PLAN_SCHEMA)
    if not isinstance(plan, dict):
        raise ProcessError("plan generation did not return an object")

    settings = get_settings()
    relative = Path(project.slug) / "project_plan.md"
    written = safe_write_text(
        settings.nexa_projects_root, relative, render_plan_markdown(project.name, plan)
    )

    project.plan_path = str(written)
    project.plan_json = plan
    project.build_destination = plan.get("proposed_build_destination") or project.build_destination
    project.stage = "process"

    item.stage_history = [*item.stage_history, {"stage": "process", "state": "done"}]
    db.add(PipelineRun(item_id=item.id, stage="process", state="done", finished_at=utcnow()))
    db.commit()
    db.refresh(project)
    return project


def read_plan_markdown(project: Project) -> str:
    settings = get_settings()
    if not project.plan_path:
        raise ProcessError("no plan generated yet")
    target = ensure_within_root(settings.nexa_projects_root, project.plan_path)
    return target.read_text(encoding="utf-8")
