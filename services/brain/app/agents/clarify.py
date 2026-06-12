"""Clarify stage.

Reviews the plan, asks only gap closing questions, matches connected integrations, lets
the user redirect scope or build target, then updates the plan and renders a preview.
Every file write goes through the path safety gate.
"""

import html
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.agents.process import ProcessError, render_plan_markdown
from app.agents.route import _latest_record
from app.json_extract import synthesize_json
from app.models.base import utcnow
from app.models.inbox import InboxItem, PipelineRun
from app.models.project import Integration, Project
from app.safety import ensure_within_root, safe_write_text
from app.settings import get_settings

logger = logging.getLogger(__name__)

_QUESTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"questions": {"type": "array", "items": {"type": "string"}}},
    "required": ["questions"],
}


def _project_for_item(db: Session, item: InboxItem) -> Project:
    project = db.query(Project).filter(Project.item_id == item.id).first()
    if project is None:
        raise ProcessError("no project for this item")
    return project


def _questions_prompt(project: Project) -> str:
    plan = project.plan_json or {}
    return (
        "Review this plan and list only the gap closing questions whose answers would "
        "materially change the plan. Do not ask questions the plan already answers.\n\n"
        f"Summary: {plan.get('summary', '')}\n"
        f"Objective: {plan.get('objective', '')}\n"
        f"Open questions: {', '.join(plan.get('open_questions', []) or [])}\n"
        f"Likely integrations: {', '.join(plan.get('likely_integrations', []) or [])}\n"
    )


def get_clarify(
    db: Session,
    item: InboxItem,
    *,
    synthesize: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    synthesize = synthesize or synthesize_json
    project = _project_for_item(db, item)
    record = _latest_record(db, item.id)
    model_key = record.recommended_model_key if record else "general"

    result = synthesize(model_key, _questions_prompt(project), _QUESTIONS_SCHEMA)
    questions = [q for q in (result.get("questions") or []) if isinstance(q, str)]

    likely = project.plan_json.get("likely_integrations", []) if project.plan_json else []
    connected = {
        row.provider.lower(): row
        for row in db.query(Integration).filter(Integration.user_id == item.user_id).all()
    }
    suggested = []
    for provider in likely:
        row = connected.get(str(provider).lower())
        suggested.append(
            {
                "provider": provider,
                "status": "connected" if row and row.status == "connected" else "available",
                "integration_id": row.id if row else None,
            }
        )
    return {"clarifying_questions": questions, "suggested_integrations": suggested}


def _render_preview_html(project: Project) -> str:
    plan = project.plan_json or {}

    def items(key: str) -> str:
        values = plan.get(key, []) or []
        return "".join(f"<li>{html.escape(str(v))}</li>" for v in values)

    name = html.escape(project.name)
    objective = html.escape(str(plan.get("objective", "")))
    destination = html.escape(str(project.build_destination or ""))
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{name} preview</title></head><body>"
        f"<h1>{name}</h1>"
        f"<p><strong>Objective:</strong> {objective}</p>"
        f"<p><strong>Build destination:</strong> {destination}</p>"
        f"<h2>Workstreams</h2><ul>{items('workstreams')}</ul>"
        f"<h2>Deliverables</h2><ul>{items('deliverables')}</ul>"
        f"<h2>Integrations</h2><ul>"
        + "".join(
            f"<li>{html.escape(str(p))}</li>" for p in (project.selected_integrations or [])
        )
        + "</ul></body></html>\n"
    )


def _render_change_summary(answers: dict[str, str], integrations: list[str], scope: dict) -> str:
    lines = ["# Change summary", "", f"Recorded {utcnow().isoformat()}.", ""]
    if answers:
        lines.append("## Clarifying answers")
        lines.extend(f"- {q}: {a}" for q, a in answers.items())
        lines.append("")
    if integrations:
        lines.append("## Selected integrations")
        lines.extend(f"- {p}" for p in integrations)
        lines.append("")
    if scope:
        lines.append("## Scope changes")
        lines.extend(f"- {k}: {v}" for k, v in scope.items())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def apply_clarify(
    db: Session,
    item: InboxItem,
    *,
    answers: dict[str, str],
    selected_integration_ids: list[int],
    scope_changes: dict[str, Any],
) -> Project:
    settings = get_settings()
    project = _project_for_item(db, item)
    plan = dict(project.plan_json or {})

    # Resolve selected integration ids to provider names owned by the user.
    rows = (
        db.query(Integration)
        .filter(
            Integration.user_id == item.user_id,
            Integration.id.in_(selected_integration_ids or [-1]),
        )
        .all()
    )
    providers = [row.provider for row in rows]
    project.selected_integrations = providers

    # Apply a build destination change if present.
    if "build_destination" in scope_changes and scope_changes["build_destination"]:
        project.build_destination = str(scope_changes["build_destination"])
        plan["proposed_build_destination"] = project.build_destination

    plan["clarifications"] = {
        "answers": answers,
        "selected_integrations": providers,
        "scope_changes": scope_changes,
    }
    project.plan_json = plan

    # Rewrite the plan with a clarifications block, plus the change summary and preview.
    plan_md = render_plan_markdown(project.name, plan)
    if answers or scope_changes:
        extra = ["", "## Clarifications"]
        extra.extend(f"- {q}: {a}" for q, a in answers.items())
        extra.extend(f"- scope: {k} -> {v}" for k, v in scope_changes.items())
        plan_md = plan_md.rstrip() + "\n" + "\n".join(extra) + "\n"

    slug = project.slug
    safe_write_text(settings.nexa_projects_root, Path(slug) / "project_plan.md", plan_md)
    safe_write_text(
        settings.nexa_projects_root,
        Path(slug) / "change_summary.md",
        _render_change_summary(answers, providers, scope_changes),
    )
    safe_write_text(
        settings.nexa_projects_root,
        Path(slug) / "project_preview.html",
        _render_preview_html(project),
    )

    project.stage = "clarify"
    item.stage_history = [*item.stage_history, {"stage": "clarify", "state": "done"}]
    db.add(PipelineRun(item_id=item.id, stage="clarify", state="done", finished_at=utcnow()))
    db.commit()
    db.refresh(project)
    return project


def read_preview_html(project: Project) -> str:
    settings = get_settings()
    target = ensure_within_root(
        settings.nexa_projects_root, Path(project.slug) / "project_preview.html"
    )
    if not target.exists():
        raise ProcessError("no preview generated yet")
    return target.read_text(encoding="utf-8")
