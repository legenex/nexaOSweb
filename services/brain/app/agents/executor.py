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
from app.gates import SAFE_TAGS, recommend_for_payload
from app.models.project import Project
from app.models.runtime import AgentRun, AgentStep
from app.project_modes import checks_for, destination_for
from app.runtime import (
    COMPLETED_UNVERIFIED,
    COMPLETED_VERIFIED,
    SKIPPED,
    correct_step,
    create_run,
    propose_step,
    record_execution,
)
from app.safety import (
    PROTECTED_BRANCHES,
    ensure_within_root,
    is_dangerous,
    safe_write_text,
)
from app.settings import get_settings

logger = logging.getLogger(__name__)

# An executor run is an AgentRun of this kind; its plan is AgentSteps of the plan kind, and each
# applied file change is an AgentStep of the edit kind. Phase c adds check, diff, and
# approval_request steps.
EXECUTOR_KIND = "executor"
PLAN_STEP_KIND = "plan"
EDIT_STEP_KIND = "edit"
CHECK_STEP_KIND = "check"
DIFF_STEP_KIND = "diff"
APPROVAL_STEP_KIND = "approval_request"
# Phase d kinds: the merge that promotes the approved work, the rollback that reverts it, and the
# deploy whose preview and gate exist now while its concrete adapters stay stubbed preview only.
MERGE_STEP_KIND = "merge"
ROLLBACK_STEP_KIND = "rollback"
DEPLOY_STEP_KIND = "deploy"

# How long a single check may run before it is killed and recorded as a timeout failure.
CHECK_TIMEOUT_SECONDS = 300
# The full check output and the worktree diff are always spilled to a file under the runtime root
# and referenced from evidence by content_ref; only a short preview is kept inline.
_CHECK_PREVIEW_CHARS = 500
_DIFF_CAP = 16000

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

# A check and a diff run read only inside the isolated worktree, so they are classified safe and
# record their outcome without a per step gate. The single gate is the approval_request below.
_CHECK_RISK = {tag: True for tag in SAFE_TAGS}
_DIFF_RISK = {tag: True for tag in SAFE_TAGS}

# The approval_request always parks at the human gate before anything leaves the worktree, so it
# carries an unsafe tag: releasing the work is user facing and is never auto resolved.
_APPROVAL_RISK = {"user_facing": True}

# A merge runs only after its human gate is already approved, and it is reversible (the before and
# after refs back a revert), so it records its outcome without re gating. The same applies to the
# rollback steps that revert it.
_MERGE_RISK = {tag: True for tag in SAFE_TAGS}

# A deploy is irreversible and external, so it always parks at the human gate. Even once approved,
# the concrete adapters are stubbed and refuse to execute: the seam exists, the trigger does not
# fire.
_DEPLOY_RISK = {"deploy": True, "external": True, "irreversible": True, "user_facing": True}

# The executor lifecycle markers. gate after phase c parks at the approval gate; merged after the
# approved merge promotes the work; rolled_back after a rollback reverts it.
PHASE_GATE = "gate"
PHASE_MERGED = "merged"
PHASE_ROLLED_BACK = "rolled_back"

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


class GateNotApprovedError(ExecutorError):
    """Raised when an irreversible or releasing action is attempted without an approved gate."""


class DeployNotEnabledError(ExecutorError):
    """Raised when the concrete deploy trigger is invoked. Deploy ships preview only."""


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


# --- phase c: real checks, evidence, diff, and the gate -----------------------------------


def _spill(run_id: int, relative: str, content: str) -> dict:
    """Write text under the runtime root and return a content reference, never the inline body.

    The full check output and the worktree diff are persisted by reference so the row carries
    only a path, a byte count, and a short preview, never the whole output.
    """
    settings = get_settings()
    rel = str(Path(f"run_{run_id}") / relative)
    safe_write_text(settings.nexa_runtime_root, rel, content)
    return {
        "ref": rel,
        "bytes": len(content.encode("utf-8")),
        "preview": content[:_CHECK_PREVIEW_CHARS],
    }


def _run_one_check(worktree: Path, run_id: int, check: dict, timeout: int) -> tuple[dict, str]:
    """Run one check inside the worktree. Returns (tool evidence, outcome).

    The dangerous-command guard refuses anything is_dangerous flags: it is recorded ran false,
    never a pass. A missing executable is also ran false. A real run captures the true exit code
    and spills stdout and stderr by reference. outcome is completed (exit 0), failed (nonzero or
    timeout), or blocked (could not run): a check that cannot run never verifies.
    """
    name = str(check["name"])
    command = [str(part) for part in check["command"]]
    command_str = " ".join(command)
    evidence: dict = {"source": "tool", "tool": "check", "name": name, "command": command_str}

    if is_dangerous(command_str):
        evidence.update(
            {
                "ran": False,
                "passed": False,
                "exit_code": None,
                "reason": "refused: dangerous command",
            }
        )
        return evidence, "blocked"

    try:
        result = subprocess.run(
            command, cwd=str(worktree), capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError:
        evidence.update(
            {
                "ran": False,
                "passed": False,
                "exit_code": None,
                "reason": f"executable not found: {command[0]}",
            }
        )
        return evidence, "blocked"
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        out = _spill(run_id, f"checks/{name}.stdout.txt", stdout)
        err = _spill(run_id, f"checks/{name}.stderr.txt", stderr)
        evidence.update(
            {
                "ran": True,
                "passed": False,
                "exit_code": None,
                "timed_out": True,
                "reason": f"timed out after {timeout}s",
                "stdout_ref": out["ref"],
                "stdout_bytes": out["bytes"],
                "stderr_ref": err["ref"],
                "stderr_bytes": err["bytes"],
            }
        )
        return evidence, "failed"

    out = _spill(run_id, f"checks/{name}.stdout.txt", result.stdout or "")
    err = _spill(run_id, f"checks/{name}.stderr.txt", result.stderr or "")
    passed = result.returncode == 0
    evidence.update(
        {
            "ran": True,
            "passed": passed,
            "exit_code": result.returncode,
            "stdout_ref": out["ref"],
            "stdout_bytes": out["bytes"],
            "stdout_preview": out["preview"],
            "stderr_ref": err["ref"],
            "stderr_bytes": err["bytes"],
            "stderr_preview": err["preview"],
        }
    )
    return evidence, ("completed" if passed else "failed")


def run_checks(
    db: Session,
    run: AgentRun,
    *,
    checks: list[dict] | None = None,
    timeout: int = CHECK_TIMEOUT_SECONDS,
    proposed_by: str = "system",
) -> list[AgentStep]:
    """Run the mode's checks inside the worktree, one check-kind step each, with tool evidence.

    Defaults to the project mode's checks; a caller may pass an explicit list. Every check is run
    through the dangerous-command guard, on a non protected branch only, inside the isolated
    worktree. A passing check lands completed_verified on its tool evidence; a failing check lands
    failed with the real exit code; a check that cannot run lands blocked, recorded honestly and
    never verified.
    """
    if run.kind != EXECUTOR_KIND:
        raise ExecutorError("checks run only on an executor run")
    if run.branch_ref in PROTECTED_BRANCHES:
        raise ExecutorError(f"refused to run checks on a protected branch: {run.branch_ref}")
    worktree = _worktree_root(run)
    if not worktree.is_dir():
        raise ExecutorError(f"worktree does not exist: {worktree}")
    project = db.get(Project, run.project_id) if run.project_id is not None else None
    if project is None:
        raise ExecutorError("an executor run requires a project to check")

    if checks is None:
        checks = [{"name": c.name, "command": list(c.command)} for c in checks_for(project.mode)]

    steps: list[AgentStep] = []
    for check in checks:
        evidence, outcome = _run_one_check(worktree, run.id, check, timeout)
        step = propose_step(
            db,
            run,
            kind=CHECK_STEP_KIND,
            title=f"Check {check['name']}",
            intent=f"Run the {check['name']} check: {' '.join(str(p) for p in check['command'])}",
            payload={
                "check": {
                    "name": str(check["name"]),
                    "command": evidence["command"],
                    "ran": evidence["ran"],
                    "passed": evidence["passed"],
                    "exit_code": evidence.get("exit_code"),
                },
                "risk": dict(_CHECK_RISK),
            },
            proposed_by=proposed_by,
        )
        failure = (
            None
            if outcome == "completed"
            else {
                "name": str(check["name"]),
                "exit_code": evidence.get("exit_code"),
                "reason": evidence.get("reason"),
            }
        )
        record_execution(db, step, outcome=outcome, evidence=[evidence], failure=failure)
        steps.append(step)
    return steps


def compute_diff_step(db: Session, run: AgentRun, *, proposed_by: str = "system") -> AgentStep:
    """Record the worktree diff versus the branch base as a diff-kind step.

    The base is the worktree HEAD the branch was cut from (phase b commits nothing). All changes,
    new files included, are staged inside the isolated worktree and diffed against that base. The
    full diff is spilled by reference and the diff-kind step carries the shortstat summary, capped.
    """
    if run.kind != EXECUTOR_KIND:
        raise ExecutorError("a diff runs only on an executor run")
    worktree = _worktree_root(run)
    if not worktree.is_dir():
        raise ExecutorError(f"worktree does not exist: {worktree}")

    base = _run_git(worktree, "rev-parse", "HEAD").strip()
    # Stage everything inside the isolated worktree so new files appear in the diff; nothing
    # leaves the worktree and no commit is made.
    _run_git(worktree, *_GIT_USER, "add", "-A")
    full = _run_git(worktree, "diff", "--cached")
    shortstat = _run_git(worktree, "diff", "--cached", "--shortstat").strip()
    capped = len(full) > _DIFF_CAP
    spilled = _spill(run.id, "diff/worktree.diff", full)

    step = propose_step(
        db,
        run,
        kind=DIFF_STEP_KIND,
        title="Worktree diff versus base",
        intent=f"Diff of the worktree against base {base[:12]}",
        payload={
            "diff": {
                "base": base,
                "shortstat": shortstat or "no changes",
                "capped": capped,
                "bytes": spilled["bytes"],
            },
            "risk": dict(_DIFF_RISK),
        },
        proposed_by=proposed_by,
    )
    record_execution(
        db,
        step,
        outcome="completed",
        evidence=[
            {
                "source": "tool",
                "tool": "git_diff",
                "base": base,
                "shortstat": shortstat,
                "capped": capped,
                "diff_ref": spilled["ref"],
                "diff_bytes": spilled["bytes"],
                "diff_preview": spilled["preview"],
            }
        ],
    )
    return step


def _checks_summary(check_steps: list[AgentStep]) -> dict:
    """Roll the check steps up into passed, failed, and cannot_run name lists for the gate."""
    summary: dict[str, list[str]] = {"passed": [], "failed": [], "cannot_run": []}
    for step in check_steps:
        check = step.payload.get("check", {}) if isinstance(step.payload, dict) else {}
        name = str(check.get("name", ""))
        if not check.get("ran"):
            summary["cannot_run"].append(name)
        elif check.get("passed"):
            summary["passed"].append(name)
        else:
            summary["failed"].append(name)
    return summary


def request_approval(
    db: Session,
    run: AgentRun,
    *,
    checks_summary: dict,
    proposed_by: str = "system",
) -> AgentStep:
    """Park the run at the human gate before anything leaves the worktree.

    The approval_request carries the checks summary and the recommended default from the gates,
    computed over its own payload so nothing authored is mutated after the fact. It is classified
    user facing, so it always lands at waiting_approval.
    """
    payload = {
        "approval_request": {
            "phase": PHASE_GATE,
            "checks": checks_summary,
            "note": "Approve before anything leaves the isolated worktree.",
        },
        "risk": dict(_APPROVAL_RISK),
    }
    payload["approval_request"]["gate"] = recommend_for_payload(payload)
    return propose_step(
        db,
        run,
        kind=APPROVAL_STEP_KIND,
        title="Approve before leaving the worktree",
        intent="Human gate: approve before anything leaves the isolated worktree.",
        payload=payload,
        proposed_by=proposed_by,
    )


def run_checks_and_gate(
    db: Session,
    run: AgentRun,
    *,
    checks: list[dict] | None = None,
    timeout: int = CHECK_TIMEOUT_SECONDS,
    proposed_by: str = "system",
) -> dict:
    """Phase c: run the checks, record the diff, and park at the human gate.

    Runs the mode's checks with real exit codes and tool evidence, records the worktree diff, then
    proposes the approval_request that holds the run at waiting_approval before anything leaves the
    worktree. This phase performs no merge and pushes nothing: the gate is the boundary.
    """
    if run.kind != EXECUTOR_KIND:
        raise ExecutorError("phase c runs only on an executor run")
    if run.branch_ref in PROTECTED_BRANCHES:
        raise ExecutorError(f"refused to run on a protected branch: {run.branch_ref}")

    check_steps = run_checks(db, run, checks=checks, timeout=timeout, proposed_by=proposed_by)
    diff_step = compute_diff_step(db, run, proposed_by=proposed_by)
    summary = _checks_summary(check_steps)
    approval_step = request_approval(db, run, checks_summary=summary, proposed_by=proposed_by)

    run.phase = PHASE_GATE
    db.commit()
    db.refresh(run)
    return {
        "check_steps": check_steps,
        "diff_step": diff_step,
        "approval_step": approval_step,
        "summary": summary,
    }


# --- phase d: gated merge, rollback, and preview-only deploy -------------------------------


def _source_repo(project: Project) -> Path:
    """The served project folder, re-gated under the projects root, the merge target."""
    settings = get_settings()
    return ensure_within_root(settings.nexa_projects_root, project.slug)


def _run_steps_of_kind(db: Session, run: AgentRun, kind: str) -> list[AgentStep]:
    return (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run.id, AgentStep.kind == kind)
        .order_by(AgentStep.seq.asc(), AgentStep.id.asc())
        .all()
    )


def _approved_gate(db: Session, run: AgentRun) -> AgentStep | None:
    """The approval_request step a human has approved, if any. The merge precondition."""
    for step in _run_steps_of_kind(db, run, APPROVAL_STEP_KIND):
        approval = step.approval if isinstance(step.approval, dict) else None
        if approval and approval.get("resolution") == "approved":
            return step
    return None


def merge_on_approval(db: Session, run: AgentRun, *, proposed_by: str = "system") -> AgentStep:
    """On an approved gate, merge the worktree branch and promote files into the served folder.

    The approval_request gate must already be approved: without it the merge is refused and the
    served folder is never touched. The approved worktree work is committed on its branch, then
    merged into the project working branch with a merge commit (history advances, never a rewrite,
    so the protected-branch rule holds). Each promoted file is validated through the path safety
    gate. The merge-kind step records the before and after refs that back a rollback.
    """
    if run.kind != EXECUTOR_KIND:
        raise ExecutorError("a merge runs only on an executor run")
    gate = _approved_gate(db, run)
    if gate is None:
        raise GateNotApprovedError("merge requires an approved gate; nothing leaves the worktree")

    branch = run.branch_ref
    if not branch or branch in PROTECTED_BRANCHES:
        raise ExecutorError(f"refused to merge an invalid or protected source branch: {branch}")
    worktree = _worktree_root(run)
    if not worktree.is_dir():
        raise ExecutorError(f"worktree does not exist: {worktree}")
    project = db.get(Project, run.project_id) if run.project_id is not None else None
    if project is None:
        raise ExecutorError("an executor run requires a project to merge into")
    source = _source_repo(project)
    working_branch = _run_git(source, "rev-parse", "--abbrev-ref", "HEAD").strip()

    # Commit the approved work on the worktree branch so there is a commit to merge.
    commit_message = f"executor run {run.id}: approved edits"
    _run_git(worktree, *_GIT_USER, "add", "-A")
    _run_git(worktree, *_GIT_USER, "commit", "-m", commit_message, "--allow-empty")

    before_ref = _run_git(source, "rev-parse", "HEAD").strip()
    _run_git(source, *_GIT_USER, "merge", "--no-ff", "--no-edit", branch)
    after_ref = _run_git(source, "rev-parse", "HEAD").strip()

    # The promoted files, each validated through the path safety gate rooted at the served folder.
    names = [
        line.strip()
        for line in _run_git(source, "diff", "--name-only", before_ref, after_ref).splitlines()
        if line.strip()
    ]
    for name in names:
        ensure_within_root(source, name)  # refuse any promoted path that escapes the served folder

    step = propose_step(
        db,
        run,
        kind=MERGE_STEP_KIND,
        title=f"Merge {branch} into {working_branch}",
        intent=f"Merge approved worktree branch {branch} into {working_branch} and promote files",
        payload={
            "merge": {
                "branch": branch,
                "working_branch": working_branch,
                "before_ref": before_ref,
                "after_ref": after_ref,
                "files": names,
                "gate_step_id": gate.id,
            },
            "risk": dict(_MERGE_RISK),
        },
        proposed_by=proposed_by,
    )
    record_execution(
        db,
        step,
        outcome="completed",
        evidence=[
            {
                "source": "tool",
                "tool": "git_merge",
                "working_branch": working_branch,
                "before_ref": before_ref,
                "after_ref": after_ref,
                "files": names,
            }
        ],
    )
    run.phase = PHASE_MERGED
    db.commit()
    db.refresh(run)
    return step


def rollback_executor_run(
    db: Session, run: AgentRun, *, proposed_by: str = "system"
) -> AgentRun:
    """Roll back the run's merges, replaying them in reverse, and mark the run rolled_back.

    Each merge is reverted on the project working branch with a revert commit (history advances,
    never a rewrite, so the protected-branch rule holds), which restores the prior content. A
    rollback-kind step records each revert, the reverted merge step is marked reverted, and the run
    is flagged rolled_back.
    """
    if run.kind != EXECUTOR_KIND:
        raise ExecutorError("a rollback runs only on an executor run")
    project = db.get(Project, run.project_id) if run.project_id is not None else None
    if project is None:
        raise ExecutorError("an executor run requires a project to roll back")
    source = _source_repo(project)

    merges = [
        step
        for step in _run_steps_of_kind(db, run, MERGE_STEP_KIND)
        if step.status in (COMPLETED_VERIFIED, COMPLETED_UNVERIFIED)
    ]
    rollbacks: list[AgentStep] = []
    for step in reversed(merges):
        info = step.payload.get("merge", {}) if isinstance(step.payload, dict) else {}
        after_ref = str(info.get("after_ref", ""))
        before_ref = str(info.get("before_ref", ""))
        # Revert the merge: a new forward commit that restores prior content, never a force.
        _run_git(source, *_GIT_USER, "revert", "--no-edit", "-m", "1", after_ref)
        revert_head = _run_git(source, "rev-parse", "HEAD").strip()

        rb = propose_step(
            db,
            run,
            kind=ROLLBACK_STEP_KIND,
            title=f"Revert merge of {info.get('branch', '')}",
            intent=f"Revert merge {after_ref[:12]} restoring {before_ref[:12]}",
            payload={
                "rollback": {
                    "reverted_step_id": step.id,
                    "from_ref": after_ref,
                    "to_ref": before_ref,
                    "revert_head": revert_head,
                },
                "risk": dict(_MERGE_RISK),
            },
            proposed_by=proposed_by,
        )
        record_execution(
            db,
            rb,
            outcome="completed",
            evidence=[
                {
                    "source": "tool",
                    "tool": "git_revert",
                    "reverted_ref": after_ref,
                    "restored_to": before_ref,
                    "revert_head": revert_head,
                }
            ],
        )
        correct_step(
            db,
            step,
            status=SKIPPED,
            correction_note=f"merge reverted by rollback (revert {revert_head[:12]})",
        )
        rollbacks.append(rb)

    run.phase = PHASE_ROLLED_BACK
    db.commit()
    db.refresh(run)
    return run


def preview_deploy(db: Session, run: AgentRun, *, proposed_by: str = "system") -> AgentStep:
    """Render the mandatory deploy preview and park at the gate. This never executes.

    The preview renders the full effect (target, files, destination). The deploy-kind step is
    classified irreversible and external, so it always parks at waiting_approval, carrying the
    recommended default from the gates. The concrete deploy is not performed here: execute_deploy
    refuses, so the trigger does not fire.
    """
    if run.kind != EXECUTOR_KIND:
        raise ExecutorError("a deploy runs only on an executor run")
    project = db.get(Project, run.project_id) if run.project_id is not None else None
    if project is None:
        raise ExecutorError("an executor run requires a project to deploy")
    source = _source_repo(project)
    files = [line.strip() for line in _run_git(source, "ls-files").splitlines() if line.strip()]
    destination = destination_for(project.mode)

    preview = {
        "target": project.slug,
        "files": files,
        "destination": destination,
        "effect": (
            f"Would deploy {len(files)} file(s) of '{project.name}' to {destination}. "
            "Preview only: the concrete deploy is stubbed and does not run."
        ),
    }
    payload = {
        "deploy": {"preview": preview, "executed": False, "enabled": False, "adapter": "stub"},
        "risk": dict(_DEPLOY_RISK),
    }
    payload["deploy"]["gate"] = recommend_for_payload(payload)
    return propose_step(
        db,
        run,
        kind=DEPLOY_STEP_KIND,
        title=f"Deploy preview to {destination}",
        intent=(
            f"Preview-only deploy to {destination}. Requires separate explicit approval and an "
            "enabled adapter; it does not execute."
        ),
        payload=payload,
        proposed_by=proposed_by,
    )


def execute_deploy(db: Session, run: AgentRun, step: AgentStep | None = None) -> None:
    """The deploy trigger seam. It does not fire: deploy ships preview only.

    Even with an approved deploy gate, the concrete adapters are stubbed and refuse to execute, so
    no irreversible deploy ever runs in this phase.
    """
    raise DeployNotEnabledError(
        "deploy adapters are preview-only; the concrete deploy trigger does not fire and refuses "
        "to execute until a real adapter is separately approved and enabled"
    )
