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


def _prompt(project: Project) -> str:
    objective = ""
    if isinstance(project.plan_json, dict):
        plan = project.plan_json
        objective = str(plan.get("objective") or plan.get("summary") or "")
    return (
        "Research the project below and return grounded findings, each a concrete fact, source, "
        "or recommendation worth recording.\n\n"
        f"Name: {project.name}\n"
        f"Notes: {objective or f'A project at stage {project.stage}.'}\n\n"
        "Return a one sentence summary and a findings array. Each finding has a title, a one "
        "sentence detail, and an optional url."
    )


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
