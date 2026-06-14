"""Executor phase a: isolated branch and plan.

The executor drives an approved project to a build. This first phase does the two things that
must happen before any work is attempted, and nothing more:

    1. It refuses to start at all unless readiness is satisfied. A run whose blocking knowledge
       gaps are still open never reaches the workspace step.
    2. It opens an isolated workspace (a git worktree on a fresh branch) under the gated runs root
       NEXA_RUNTIME_ROOT, through the path safety gate, and persists the plan as plan-kind steps
       read from requirements.md, the source of truth produced at promote.

This phase plans only. It creates the worktree and the branch and records the plan, but it makes
no edits inside the worktree and runs no build commands. Later phases pick the plan steps up and
execute them through the existing runtime writers. The executor builds on the existing AgentRun
and AgentStep spine: an executor run is an AgentRun of kind executor, and its plan is ordinary
AgentSteps of kind plan. There is no second run model.
"""

import logging
import re
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app.agents.readiness import readiness_satisfied
from app.gates import SAFE_TAGS
from app.models.project import Project
from app.models.runtime import AgentRun
from app.runtime import create_run, propose_step
from app.safety import PROTECTED_BRANCHES, ensure_within_root, is_dangerous
from app.settings import get_settings

logger = logging.getLogger(__name__)

# An executor run is an AgentRun of this kind; its plan is AgentSteps of the plan kind.
EXECUTOR_KIND = "executor"
PLAN_STEP_KIND = "plan"

# The executor lifecycle marker stored on AgentRun.phase. Phase a ends with the plan recorded.
PHASE_PLAN = "plan"

# A non zero autonomy so the recorded plan steps, which are pure intent and classified safe, sit
# at planned rather than the human gate. Executing them is a later phase and is gated there.
EXECUTOR_AUTONOMY = 1

# A plan step is a record of intended work, not the work itself: reversible, local, non external.
_PLAN_RISK = {tag: True for tag in SAFE_TAGS}

# Git identity used only for the baseline commit in a fresh project repo, so a commit exists to
# branch a worktree from. It never touches the user's global config.
_GIT_USER = ("-c", "user.email=executor@nexaos.local", "-c", "user.name=nexaOS executor")

# Markdown task lines (checkbox, bullet, or numbered) and section headings, in priority order.
_TASK_RE = re.compile(r"^\s*(?:[-*+]\s+\[[ xX]\]\s+|[-*+]\s+|\d+[.)]\s+)(.+?)\s*$")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")


class ExecutorError(Exception):
    """Raised when an executor run cannot be started or its workspace cannot be opened."""


class ReadinessNotSatisfiedError(ExecutorError):
    """Raised when a run is asked to start while a blocking readiness gap is still open."""


# --- the plan, read from requirements.md --------------------------------------------------


def plan_steps_from_requirements(text: str) -> list[dict]:
    """Derive an ordered plan from requirements.md.

    Task lines (checkboxes, bullets, numbered items) are preferred. With none, the section
    headings stand in (the Requirements heading itself is dropped). With neither, a single step
    to implement the requirements is returned, so a plan always has at least one step.
    """
    tasks = []
    for line in text.splitlines():
        match = _TASK_RE.match(line)
        if match and match.group(1).strip():
            tasks.append(match.group(1).strip())
    if tasks:
        return [{"title": title} for title in tasks]

    headings = []
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match and match.group(1).strip().lower() != "requirements":
            headings.append(match.group(1).strip())
    if headings:
        return [{"title": title} for title in headings]

    return [{"title": "Implement the approved requirements"}]


# --- the isolated workspace ---------------------------------------------------------------


def _run_git(cwd: Path, *args: str) -> str:
    command = ["git", *args]
    if is_dangerous(" ".join(command)):
        raise ExecutorError(f"refused dangerous command: {' '.join(command)}")
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ExecutorError(f"git {' '.join(args)} failed in {cwd}: {detail}")
    return result.stdout


def _has_commit(repo: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _ensure_source_repo(repo: Path) -> None:
    """Ensure the project folder is a git repo with at least one commit to branch from.

    A worktree needs a parent repo with a HEAD. A fresh project folder is initialised and its
    current contents (requirements.md and anything else already written through the safety gate)
    are committed as the baseline. An existing repo is left untouched.
    """
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        _run_git(repo, "init")
    if not _has_commit(repo):
        message = "executor: baseline from requirements"
        _run_git(repo, *_GIT_USER, "add", "-A")
        _run_git(repo, *_GIT_USER, "commit", "-m", message, "--allow-empty")


def _create_workspace(project: Project, run_id: int) -> tuple[str, Path]:
    """Open the isolated worktree on a fresh branch under the gated runs root.

    The branch name is derived from the run id and can never be a protected branch. The worktree
    path is resolved through ensure_within_root so a crafted slug cannot escape NEXA_RUNTIME_ROOT.
    No file inside the worktree is written here: the checkout is the baseline, unedited.
    """
    settings = get_settings()
    source = ensure_within_root(settings.nexa_projects_root, project.slug)
    _ensure_source_repo(source)

    branch_ref = f"executor/run-{run_id}"
    if branch_ref in PROTECTED_BRANCHES:  # pragma: no cover - the run-id prefix never collides
        raise ExecutorError(f"refused to branch onto a protected branch: {branch_ref}")

    worktree_path = ensure_within_root(
        settings.nexa_runtime_root, Path("worktrees") / f"run_{run_id}"
    )
    if worktree_path.exists():
        raise ExecutorError(f"worktree path already exists: {worktree_path}")
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    _run_git(source, *_GIT_USER, "worktree", "add", "-b", branch_ref, str(worktree_path), "HEAD")
    return branch_ref, worktree_path


# --- starting a run -----------------------------------------------------------------------


def _read_requirements(project: Project) -> str:
    settings = get_settings()
    path = ensure_within_root(
        settings.nexa_projects_root, Path(project.slug) / "requirements.md"
    )
    if not path.exists():
        raise ExecutorError("project has no requirements.md to plan from")
    return path.read_text(encoding="utf-8")


def start_executor_run(
    db: Session,
    *,
    readiness_run: AgentRun,
    project_id: int | None = None,
    proposed_by: str = "system",
) -> AgentRun:
    """Start an executor run: refuse on unsatisfied readiness, else open a workspace and plan.

    The readiness guard runs first and is absolute: if any blocking readiness item on the given
    readiness run is still open, the run is refused and nothing is created (no AgentRun, no
    branch, no worktree). Only once readiness is satisfied does the run come into being, open its
    isolated worktree on a fresh branch, and record the plan as plan-kind steps from
    requirements.md. This phase makes no edits and runs no build commands.
    """
    if not readiness_satisfied(db, readiness_run):
        raise ReadinessNotSatisfiedError(
            "cannot start an executor run while a blocking readiness item is open"
        )

    pid = project_id if project_id is not None else readiness_run.project_id
    if pid is None:
        raise ExecutorError("an executor run requires a project")
    project = db.get(Project, pid)
    if project is None:
        raise ExecutorError("project not found")

    requirements = _read_requirements(project)

    plan = readiness_run.plan if isinstance(readiness_run.plan, dict) else {}
    run = create_run(
        db,
        project_id=pid,
        autonomy_level=EXECUTOR_AUTONOMY,
        plan=plan,
        kind=EXECUTOR_KIND,
        goal_summary="Executor run: isolated branch and plan from requirements",
        proposed_by=proposed_by,
        parent_run_id=readiness_run.id,
    )

    branch_ref, worktree_path = _create_workspace(project, run.id)
    run.branch_ref = branch_ref
    run.worktree_path = str(worktree_path)
    run.phase = PHASE_PLAN
    db.commit()
    db.refresh(run)

    for index, item in enumerate(plan_steps_from_requirements(requirements)):
        propose_step(
            db,
            run,
            kind=PLAN_STEP_KIND,
            title=item["title"],
            intent=f"Planned step from requirements.md: {item['title']}",
            payload={
                "plan": {"index": index, "title": item["title"], "source": "requirements.md"},
                "risk": dict(_PLAN_RISK),
            },
            proposed_by=proposed_by,
            idempotency_key=f"plan:{index}",
        )

    db.refresh(run)
    return run
