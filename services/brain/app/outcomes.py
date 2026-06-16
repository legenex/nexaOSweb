"""The write path for the deferred outcome seam.

record_outcome upserts the one OutcomeLog row for a run from the build engine's approve, reject, and
revert paths. The verdict is the human decision that disposed of the run; reverted marks a merged
change that was later undone and is sticky, so a revert never clears a prior revert. No learning is
built on these rows now; this only records them (see docs/ARCHITECTURE.md).
"""

from sqlalchemy.orm import Session

from app.models.outcome import OutcomeLog
from app.models.runtime import AgentRun

VERDICT_APPROVED = "approved"
VERDICT_REJECTED = "rejected"
_VERDICTS = frozenset({VERDICT_APPROVED, VERDICT_REJECTED})


class OutcomeError(Exception):
    """Raised for an unknown verdict."""


def record_outcome(
    db: Session,
    run: AgentRun,
    *,
    verdict: str,
    reverted: bool = False,
    note: str = "",
) -> OutcomeLog:
    """Record (or update) the outcome of one run. At most one row per run, upserted by run_id.

    A first call creates the row. A later call updates the verdict and note, and sets reverted when
    a merged change is undone; reverted is sticky, so once true it stays true.
    """
    if verdict not in _VERDICTS:
        raise OutcomeError(f"verdict must be approved or rejected, not {verdict!r}")

    row = db.query(OutcomeLog).filter(OutcomeLog.run_id == run.id).first()
    if row is None:
        row = OutcomeLog(
            run_id=run.id,
            project_id=run.project_id,
            verdict=verdict,
            reverted=reverted,
            note=note,
        )
        db.add(row)
    else:
        row.verdict = verdict
        if reverted:
            row.reverted = True
        if note:
            row.note = note
    db.commit()
    db.refresh(row)
    return row
