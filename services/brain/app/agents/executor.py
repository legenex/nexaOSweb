"""Executor phases a and b: isolated branch and plan, then the gated edit loop.

The executor drives an approved project to a build on the existing AgentRun and AgentStep spine:
an executor run is an AgentRun of kind executor, and there is no second run model.

Phase a does the two things that must happen before any work is attempted, and nothing more:

    1. It refuses to start at all unless readiness is satisfied. A run whose blocking knowledge
       gaps are still open never reaches the workspace step.
    2. It opens an isolated workspace (a git worktree on a fresh branch) under the gated runs root
       NEXA_RUNTIME_ROOT, through the path safety gate, and persists the plan as plan-kind steps
       read from requirements.md, the source of truth produced at promote.

Phase b runs the edit loop. For each planned file change the coordinator calls the gated editor
rooted at the worktree, producing a proposed BuildLogEntry and an edit-kind AgentStep, then applies
the change to the worktree. Edits happen only inside the worktree, never the live checkout, and
every write passes ensure_within_root rooted at the worktree. Each step carries a content
idempotency key (a hash of intent plus the intended content): re-running a succeeded step is a
no-op, and an apply whose target already equals the intended content writes nothing. This phase
only edits: it runs no checks and no merges. The protected-branch guard refuses to edit on a
protected branch, and the dangerous-command guard wraps the few git commands phase a runs.
"""

import hashlib
import logging
import re
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app.agents.project_editor import apply_edit, proposed_entry, render_edit
from app.agents.readiness import readiness_satisfied
from app.gates import SAFE_TAGS
from app.models.project import Project
from app.models.runtime import AgentRun, AgentStep
from app.runtime import (
    COMPLETED_UNVERIFIED,
    COMPLETED_VERIFIED,
    create_run,
    propose_step,
    record_execution,
)
from app.safety import PROTECTED_BRANCHES, ensure_within_root, is_dangerous
from app.settings import get_settings

logger = logging.getLogger(__name__)

# An executor run is an AgentRun of this kind; its plan is AgentSteps of the plan kind, and each
# applied file change is an AgentStep of the edit kind.
EXECUTOR_KIND = "executor"
PLAN_STEP_KIND = "plan"
EDIT_STEP_KIND = "edit"

# The terminal completed states a succeeded edit step lands on, used to detect a re-run no-op.
_COMPLETED_STATES = (COMPLETED_VERIFIED, COMPLETED_UNVERIFIED)

# The executor lifecycle marker stored on AgentRun.phase. Phase a ends with the plan recorded.
PHASE_PLAN = "plan"

# A non zero autonomy so the recorded plan steps, which are pure intent and classified safe, sit
# at planned rather than the human gate. Executing them is a later phase and is gated there.
EXECUTOR_AUTONOMY = 1

# A plan step is a record of intended work, not the work itself: reversible, local, non external.
_PLAN_RISK = {tag: True for tag in SAFE_TAGS}

# An edit inside the isolated worktree is reversible (the BuildLogEntry holds the prior content),
# local to the worktree, and touches nothing external, so it is classified safe and lands planned
# at the executor's non zero autonomy rather than at the human gate.
_EDIT_RISK = {tag: True for tag in SAFE_TAGS}

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


# --- phase b: the gated edit loop ---------------------------------------------------------


def _edit_intent(file_path: str, instruction: str) -> str:
    return f"edit {file_path}: {instruction}".strip()


def _edit_idempotency_key(intent: str, intended_content: str) -> str:
    """A stable per-run key for an edit: a hash of intent plus the intended target content.

    Same intent and same intended content yield the same key, so re-proposing the unit is caught
    before a second step or a second write. The key is namespaced so it never collides with a plan
    step key.
    """
    digest = hashlib.sha256(f"{intent}\x00{intended_content}".encode()).hexdigest()
    return f"edit:{digest[:48]}"


def _succeeded_edit_step(db: Session, run: AgentRun, key: str) -> AgentStep | None:
    """An already completed edit step for this exact unit, if one exists in the run."""
    return (
        db.query(AgentStep)
        .filter(
            AgentStep.run_id == run.id,
            AgentStep.idempotency_key == key,
            AgentStep.status.in_(_COMPLETED_STATES),
        )
        .first()
    )


def _worktree_root(run: AgentRun) -> Path:
    """The run's worktree, re-gated under the runtime root so a stored path is never trusted."""
    if not run.worktree_path:
        raise ExecutorError("executor run has no worktree to edit in")
    settings = get_settings()
    return ensure_within_root(settings.nexa_runtime_root, run.worktree_path)


def _apply_one_edit(
    db: Session,
    run: AgentRun,
    project: Project,
    worktree: Path,
    change: dict,
    synthesize,
    proposed_by: str,
) -> AgentStep:
    """Propose and apply a single file change inside the worktree, idempotently.

    The gated editor renders the intended content rooted at the worktree (the path gate runs
    there). If a completed step already covers this exact unit, nothing new is created. Otherwise
    a proposed BuildLogEntry and an edit-kind step are recorded, and the change is applied to the
    worktree, unless the target already holds the intended content, in which case no write occurs.
    """
    file_path = str(change["file_path"])
    instruction = str(change.get("instruction", ""))
    intent = _edit_intent(file_path, instruction)

    rendered = render_edit(
        project,
        file_path=file_path,
        instruction=instruction,
        synthesize=synthesize,
        root=worktree,
    )
    key = _edit_idempotency_key(intent, rendered.after)

    # Step-level idempotency: a succeeded step for this unit is a no-op, with no new step, entry,
    # or write. This is what makes re-running an applied edit safe.
    existing = _succeeded_edit_step(db, run, key)
    if existing is not None:
        return existing

    entry = proposed_entry(db, project, rendered)
    step = propose_step(
        db,
        run,
        kind=EDIT_STEP_KIND,
        title=f"Edit {file_path}",
        intent=intent,
        payload={
            "edit": {
                "file_path": file_path,
                "build_log_id": entry.id,
                "summary": entry.summary,
            },
            "risk": dict(_EDIT_RISK),
        },
        proposed_by=proposed_by,
        idempotency_key=key,
    )

    # Content-level idempotency: only write when the target is not already the intended content.
    target = ensure_within_root(worktree, file_path)
    already_current = target.exists() and target.read_text(encoding="utf-8") == rendered.after
    if already_current:
        entry.status = "applied"  # the desired content is present; record applied without a write
        db.commit()
        wrote = False
        written_path = str(target)
    else:
        written_path = apply_edit(db, project, entry, root=worktree)
        wrote = True

    evidence = [
        {
            "source": "tool",
            "tool": "gated_editor",
            "file_path": file_path,
            "build_log_id": entry.id,
            "wrote": wrote,
            "written_path": written_path,
        }
    ]
    record_execution(db, step, outcome="completed", evidence=evidence)
    return step


def execute_planned_edits(
    db: Session,
    run: AgentRun,
    changes: list[dict],
    *,
    synthesize=None,
    proposed_by: str = "system",
) -> list[AgentStep]:
    """Run the gated edit loop for an executor run, applying each change inside the worktree.

    A change is a dict with a file_path and an instruction. Every edit is confined to the run's
    worktree by ensure_within_root and never touches the live checkout. The protected-branch guard
    refuses to edit on a protected branch. This phase only edits: it runs no checks and no merges.
    Returns the edit step per change, the same step instance for a unit already satisfied.
    """
    if run.kind != EXECUTOR_KIND:
        raise ExecutorError("edits run only on an executor run")
    if run.branch_ref in PROTECTED_BRANCHES:
        raise ExecutorError(f"refused to edit on a protected branch: {run.branch_ref}")

    worktree = _worktree_root(run)
    if not worktree.is_dir():
        raise ExecutorError(f"worktree does not exist: {worktree}")
    project = db.get(Project, run.project_id) if run.project_id is not None else None
    if project is None:
        raise ExecutorError("an executor run requires a project to edit")

    steps: list[AgentStep] = []
    for change in changes:
        if not isinstance(change, dict) or not change.get("file_path"):
            raise ExecutorError("each change needs a file_path")
        steps.append(
            _apply_one_edit(db, run, project, worktree, change, synthesize, proposed_by)
        )
    db.refresh(run)
    return steps
