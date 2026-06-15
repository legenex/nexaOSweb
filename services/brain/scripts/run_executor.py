"""Watched executor entrypoint. Runs the gated loop on a project and parks at the human gate.

Usage: python -m scripts.run_executor <project_id>

This is the trigger the executor library was missing: nothing else calls start_executor_run
outside tests. It drives the full loop on one project:

  readiness -> start_executor_run -> plan from requirements -> model backed edits -> checks ->
  the human approval gate.

The edits are rendered by synthesize_json, which resolves the agentic_code semantic key through
the router (store first provider key, no hardcoded model id) and falls back to a deterministic
offline rendering when no provider is connected, so the loop is watchable with or without a key.

The run stops at the approval gate. Nothing is ever merged here: merge_on_approval is a separate,
human gated step and this entrypoint never calls it.
"""

import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.agents.executor import (
    execute_planned_edits,
    plan_steps_from_requirements,
    run_checks_and_gate,
    start_executor_run,
)
from app.agents.readiness import evaluate_readiness, readiness_satisfied
from app.db import SessionLocal
from app.json_extract import synthesize_json
from app.models.project import Project
from app.models.runtime import AgentStep
from app.settings import get_settings
from app.util import slugify


def _requirements_text(project: Project) -> str:
    settings = get_settings()
    path = Path(settings.nexa_projects_root) / project.slug / "requirements.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _changes_from_plan(plan: list[dict]) -> list[dict]:
    """Turn planned titles into concrete, worktree confined edit instructions.

    Each plan step becomes a distinct notes file so edits never clobber one another. A real
    multi agent planner will choose target files itself; this keeps the watched run concrete.
    """
    changes: list[dict] = []
    for index, step in enumerate(plan, start=1):
        title = str(step.get("title", "task"))
        changes.append(
            {
                "file_path": f"docs/plan/{index:02d}-{slugify(title)}.md",
                "instruction": f"Write the implementation notes for: {title}",
            }
        )
    return changes


def run_executor(db: Session, project_id: int, *, checks: list[dict] | None = None) -> dict:
    """Run the loop and return a summary. Parks at the gate; never merges."""
    project = db.get(Project, project_id)
    if project is None:
        raise SystemExit(f"project {project_id} not found")

    readiness = evaluate_readiness(db, plan=project.plan_json or {}, project_id=project.id)
    if not readiness_satisfied(db, readiness):
        print("readiness not satisfied: resolve the blocking items before running the executor")
        return {"run_id": None, "status": "blocked_on_readiness"}

    run = start_executor_run(db, readiness_run=readiness, project_id=project.id)
    print(f"run {run.id} started on branch {run.branch_ref} (worktree {run.worktree_path})")

    plan = plan_steps_from_requirements(_requirements_text(project))
    edit_steps = execute_planned_edits(
        db, run, _changes_from_plan(plan), synthesize=synthesize_json
    )
    print(f"applied {len(edit_steps)} model sourced edit steps")

    run_checks_and_gate(db, run, checks=checks)

    steps = (
        db.query(AgentStep).filter(AgentStep.run_id == run.id).order_by(AgentStep.seq.asc()).all()
    )
    for step in steps:
        print(f"  [{step.seq:>2}] {step.kind:<16} {step.status:<22} {step.title}")
    print(f"run status: {run.status}. Parked at the gate, nothing merged.")
    return {"run_id": run.id, "status": run.status, "steps": len(steps)}


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m scripts.run_executor <project_id>")
        raise SystemExit(2)
    db = SessionLocal()
    try:
        run_executor(db, int(sys.argv[1]))
    finally:
        db.close()


if __name__ == "__main__":
    main()
