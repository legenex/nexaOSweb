"""Research run service.

A research run asks the research_synthesis model for grounded findings about a project. When
the research project is attached to a build project, each finding is posted into that build
project's Update Log on completion. The model is selected by semantic key, never by id.
"""

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.json_extract import synthesize_json
from app.models.base import utcnow
from app.models.project import Project
from app.models.research import ProjectUpdate, ResearchFinding, ResearchRun

logger = logging.getLogger(__name__)

# Findings are synthesised with the research_synthesis key. Swapping the model is a config change.
RESEARCH_MODEL_KEY = "research_synthesis"

Synthesizer = Callable[..., dict[str, Any]]

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "analysis": {"type": "string"},
        "key_takeaways": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["title"],
            },
        },
    },
    "required": ["summary", "findings"],
}

# The shape generate-config drafts from a topic, ready for the user to edit before Create.
_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "purpose": {"type": "string"},
        "goals": {"type": "array", "items": {"type": "string"}},
        "depth": {"type": "string", "enum": ["quick", "standard", "deep"]},
        "lookback": {"type": "integer"},
        "schedule": {"type": "string", "enum": ["off", "daily", "weekly"]},
    },
    "required": ["purpose", "goals", "depth", "lookback", "schedule"],
}


def _prompt(project: Project) -> str:
    config = project.research_config or {}
    topic = str(config.get("topic") or "")
    purpose = str(config.get("purpose") or "")
    goals = config.get("goals") or []
    if not topic and isinstance(project.plan_json, dict):
        topic = str(project.plan_json.get("objective") or project.plan_json.get("summary") or "")
    goals_line = "; ".join(str(g) for g in goals) if isinstance(goals, list) else ""
    return (
        "Research the topic below and return grounded findings, each a concrete fact, source, or "
        "recommendation worth recording.\n\n"
        f"Name: {project.name}\n"
        f"Topic: {topic or project.name}\n"
        f"Purpose: {purpose or 'general understanding'}\n"
        f"Goals: {goals_line or 'none specified'}\n\n"
        "Return a one sentence summary, an analysis paragraph, key_takeaways and suggestions as "
        "short string arrays, and a findings array. Each finding has a title, a one sentence "
        "detail, and an optional url."
    )


def _coerce_strings(raw: Any, limit: int = 12) -> list[str]:
    out: list[str] = []
    for entry in raw or []:
        text = str(entry).strip()
        if text:
            out.append(text[:300])
        if len(out) >= limit:
            break
    return out


def _coerce_findings(raw: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for entry in raw or []:
        if isinstance(entry, str):
            findings.append({"title": entry.strip()[:300] or "Finding", "detail": "", "url": None})
        elif isinstance(entry, dict):
            title = str(entry.get("title") or entry.get("name") or "Finding").strip()[:300]
            detail = str(
                entry.get("detail") or entry.get("body") or entry.get("summary") or ""
            ).strip()
            url = entry.get("url")
            findings.append(
                {"title": title or "Finding", "detail": detail, "url": str(url) if url else None}
            )
    return findings


def run_research(
    db: Session,
    project: Project,
    *,
    synthesize: Synthesizer | None = None,
) -> ResearchRun:
    """Run one research pass. On completion, post findings into the attached build project."""
    synthesize = synthesize or synthesize_json
    run = ResearchRun(project_id=project.id, status="running", summary="")
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        result = synthesize(RESEARCH_MODEL_KEY, _prompt(project), _SCHEMA)
        summary = str(result.get("summary", "")).strip()
        findings = _coerce_findings(result.get("findings"))
        target_id = project.research_target_id

        for entry in findings:
            finding = ResearchFinding(
                project_id=project.id,
                run_id=run.id,
                title=entry["title"],
                detail=entry["detail"],
                url=entry["url"],
                status="new",
            )
            db.add(finding)
            db.flush()  # assign finding.id before referencing it
            if target_id is not None:
                db.add(
                    ProjectUpdate(
                        project_id=target_id,
                        kind="research_finding",
                        title=finding.title,
                        body=finding.detail,
                        source_ref={
                            "type": "research_finding",
                            "finding_id": finding.id,
                            "research_project_id": project.id,
                            "run_id": run.id,
                        },
                    )
                )

        run.summary = summary
        run.analysis = str(result.get("analysis", "")).strip()
        run.key_takeaways = _coerce_strings(result.get("key_takeaways"))
        run.suggestions = _coerce_strings(result.get("suggestions"))
        run.findings_count = len(findings)
        run.status = "completed"
        run.finished_at = utcnow()
        db.commit()
        db.refresh(run)
        return run
    except Exception:
        db.rollback()
        run.status = "failed"
        run.finished_at = utcnow()
        db.commit()
        raise


def generate_config(
    topic: str,
    name: str = "",
    *,
    synthesize: Synthesizer | None = None,
) -> dict[str, Any]:
    """Draft a research config (purpose, goals, depth, lookback, schedule) from a topic."""
    synthesize = synthesize or synthesize_json
    prompt = (
        "Draft a research configuration for the topic below.\n\n"
        f"Name: {name or topic}\n"
        f"Topic: {topic}\n\n"
        "Return a one sentence purpose, three to five concrete goals, a depth of quick, standard, "
        "or deep, a lookback in days, and a schedule of off, daily, or weekly."
    )
    result = synthesize(RESEARCH_MODEL_KEY, prompt, _CONFIG_SCHEMA)

    depth = result.get("depth")
    if depth not in ("quick", "standard", "deep"):
        depth = "standard"
    schedule = result.get("schedule")
    if schedule not in ("off", "daily", "weekly"):
        schedule = "off"
    try:
        lookback = max(1, min(3650, int(result.get("lookback", 30))))
    except (TypeError, ValueError):
        lookback = 30

    return {
        "purpose": str(result.get("purpose", "")).strip(),
        "goals": _coerce_strings(result.get("goals")),
        "depth": depth,
        "lookback": lookback,
        "schedule": schedule,
    }
