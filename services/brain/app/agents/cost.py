"""Project cost accounting: per backend rollups, run cost estimates, and budget enforcement.

The figures are the real ones the backends reported and the build engine recorded: cost_usd is
denormalised on each build run, the token counts live on each run's build step evidence. This module
reads that stored truth, never a fresh model call.

  - project_cost_rollup sums a project's spend and token usage, broken down by backend, for the
    cost surface.
  - estimate_backend_costs projects a per backend cost for the next run from the project's history,
    so the selector can skip a backend that would run over its configured ceiling.
  - project_budget, project_spend_since, and budget_status back the daily and monthly project
    budget that pauses dispatch when breached. The budget lives in AppSetting, default unlimited, so
    it tunes without a schema change.

This module imports only models at load time. run_usage lives in build_engine; project_cost_rollup
imports it lazily inside the call so the two modules do not form an import cycle.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.runtime import AgentRun
from app.models.workspace import AppSetting

# The project budget lives under one global AppSetting row per project (user_id null), because a
# budget is a project policy, not a per user preference. Default unlimited: None means no ceiling.
PROJECT_BUDGET_KEY_PREFIX = "agent_budget:"
PROJECT_BUDGET_DEFAULTS: dict[str, float | None] = {"daily_usd": None, "monthly_usd": None}


def _budget_key(project_id: int) -> str:
    return f"{PROJECT_BUDGET_KEY_PREFIX}{project_id}"


def _build_runs(db: Session, project_id: int):
    """A project's build runs: executor-kind runs an external backend drove (a non-null backend)."""
    return (
        db.query(AgentRun)
        .filter(AgentRun.project_id == project_id, AgentRun.backend.isnot(None))
        .all()
    )


def project_cost_rollup(db: Session, project_id: int) -> dict:
    """Sum a project's agent spend and token usage, broken down by backend.

    Reads the same per run usage the read detail surfaces (run_usage), so the rollup and the detail
    never disagree. by_backend is sorted by backend name for a stable response.
    """
    from app.agents.build_engine import run_usage

    by_backend: dict[str, dict] = {}
    total_cost = 0.0
    total_input = 0
    total_output = 0
    runs = _build_runs(db, project_id)
    for run in runs:
        usage = run_usage(db, run)
        cost = usage["cost_usd"] or 0.0
        input_tokens = usage["input_tokens"] or 0
        output_tokens = usage["output_tokens"] or 0
        bucket = by_backend.setdefault(
            run.backend,
            {"backend": run.backend, "run_count": 0, "cost_usd": 0.0,
             "input_tokens": 0, "output_tokens": 0},
        )
        bucket["run_count"] += 1
        bucket["cost_usd"] += cost
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        total_cost += cost
        total_input += input_tokens
        total_output += output_tokens

    return {
        "project_id": project_id,
        "total_usd": round(total_cost, 6),
        "run_count": len(runs),
        "input_tokens": total_input,
        "output_tokens": total_output,
        "by_backend": [
            {**bucket, "cost_usd": round(bucket["cost_usd"], 6)}
            for bucket in sorted(by_backend.values(), key=lambda b: b["backend"])
        ],
    }


def estimate_backend_costs(db: Session, project_id: int) -> dict[str, float]:
    """Project a per backend cost for the next run from this project's history.

    The estimate is the mean recorded cost of the project's prior runs on that backend. A backend
    with no history yields no estimate, so the selector never blocks a backend it cannot estimate;
    the ceiling only ever skips a backend whose projected cost is known to exceed it.
    """
    rows = (
        db.query(AgentRun.backend, AgentRun.cost_usd)
        .filter(
            AgentRun.project_id == project_id,
            AgentRun.backend.isnot(None),
            AgentRun.cost_usd.isnot(None),
        )
        .all()
    )
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for backend, cost in rows:
        sums[backend] = sums.get(backend, 0.0) + float(cost)
        counts[backend] = counts.get(backend, 0) + 1
    return {backend: sums[backend] / counts[backend] for backend in sums}


def project_budget(db: Session, project_id: int) -> dict[str, float | None]:
    """The project's daily and monthly budget in USD, the unlimited defaults merged with any set."""
    values = dict(PROJECT_BUDGET_DEFAULTS)
    row = (
        db.query(AppSetting)
        .filter(AppSetting.user_id.is_(None), AppSetting.key == _budget_key(project_id))
        .first()
    )
    if row and isinstance(row.value, dict):
        values.update({k: v for k, v in row.value.items() if k in values})
    return values


def set_project_budget(
    db: Session,
    project_id: int,
    *,
    daily_usd: float | None = None,
    monthly_usd: float | None = None,
) -> dict[str, float | None]:
    """Set a project's daily and monthly budget. None for a field means unlimited for that one."""
    values: dict[str, float | None] = {"daily_usd": daily_usd, "monthly_usd": monthly_usd}
    row = (
        db.query(AppSetting)
        .filter(AppSetting.user_id.is_(None), AppSetting.key == _budget_key(project_id))
        .first()
    )
    if row is None:
        db.add(AppSetting(user_id=None, key=_budget_key(project_id), value=values))
    else:
        row.value = values
    db.commit()
    return project_budget(db, project_id)


def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def project_spend_since(db: Session, project_id: int, since: datetime) -> float:
    """The project's recorded agent spend in USD since a point in time."""
    rows = (
        db.query(AgentRun.cost_usd)
        .filter(
            AgentRun.project_id == project_id,
            AgentRun.backend.isnot(None),
            AgentRun.cost_usd.isnot(None),
            AgentRun.created_at >= since,
        )
        .all()
    )
    return float(sum(row[0] for row in rows))


def budget_status(db: Session, project_id: int) -> dict:
    """The project's budget, its current daily and monthly spend, and whether either is breached.

    A None budget for a window is unlimited and never breached. The daily window is checked before
    the monthly window so the reported scope is the tightest one breached.
    """
    budget = project_budget(db, project_id)
    now = utcnow()
    daily_spend = project_spend_since(db, project_id, _day_start(now))
    monthly_spend = project_spend_since(db, project_id, _month_start(now))

    exceeded = False
    scope: str | None = None
    if budget["daily_usd"] is not None and daily_spend >= budget["daily_usd"]:
        exceeded, scope = True, "daily"
    elif budget["monthly_usd"] is not None and monthly_spend >= budget["monthly_usd"]:
        exceeded, scope = True, "monthly"

    return {
        "project_id": project_id,
        "exceeded": exceeded,
        "scope": scope,
        "daily_usd": budget["daily_usd"],
        "monthly_usd": budget["monthly_usd"],
        "daily_spend": round(daily_spend, 6),
        "monthly_spend": round(monthly_spend, 6),
    }
