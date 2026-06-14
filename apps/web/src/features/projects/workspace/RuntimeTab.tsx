import { useCallback, useEffect, useRef, useState } from 'react';

import { OverflowMenu } from '../../../components/OverflowMenu';
import { MonoLabel, Pill, StatusDot } from '../../../components/primitives';
import type { DotState } from '../../../components/primitives';
import { useConnectionMonitor } from '../../../app/useConnectionMonitor';
import { ProofOfWork, VerificationBadge } from './ProofOfWork';
import {
  deriveRunStatus,
  getRun,
  getStepsAfter,
  listRuns,
  mergeSteps,
  settledBoundary,
} from './runtimeApi';
import type { Run, RunWithSteps, Step } from './runtimeApi';

const STEP_DOT: Record<string, DotState> = {
  planned: 'pending',
  waiting_approval: 'gate',
  blocked: 'warn',
  executing: 'current',
  completed_verified: 'live',
  completed_unverified: 'done',
  failed: 'error',
  skipped: 'pending',
};

const POLL_MS = 4000;

function StepRow({ step }: { step: Step }) {
  return (
    <li className="rounded-glass border border-line bg-surface/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <MonoLabel tone="faint">#{step.seq}</MonoLabel>
        <StatusDot state={STEP_DOT[step.status] ?? 'pending'} label={step.status} />
        <span className="text-sm font-semibold text-cream">{step.title || step.kind}</span>
        <Pill variant="grey">{step.kind}</Pill>
        <Pill variant="accent">{step.status}</Pill>
        <span className="ml-auto">
          <VerificationBadge step={step} />
        </span>
      </div>
      {step.intent ? <p className="mt-1 text-sm text-muted">{step.intent}</p> : null}
      <ProofOfWork step={step} />
    </li>
  );
}

// One run's live timeline. The full run loads once; thereafter the unsettled tail is polled with
// steps-after-cursor while the uplink is connected, so in-flight steps update and new steps
// appear without reloading the whole run.
function RunTimeline({ runId, onReloadRuns }: { runId: number; onReloadRuns: () => void }) {
  const { connected } = useConnectionMonitor();
  const [run, setRun] = useState<RunWithSteps | null>(null);
  const [steps, setSteps] = useState<Step[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cursorRef = useRef<number | null>(null);
  const stepsRef = useRef<Step[] | null>(null);
  stepsRef.current = steps;

  const load = useCallback(async () => {
    try {
      const fetched = await getRun(runId);
      setRun(fetched);
      setSteps(fetched.steps);
      cursorRef.current = settledBoundary(fetched.steps);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [runId]);

  useEffect(() => {
    setRun(null);
    setSteps(null);
    setError(null);
    cursorRef.current = null;
    void load();
  }, [load]);

  useEffect(() => {
    if (!connected || steps === null) return undefined;
    const id = window.setInterval(async () => {
      try {
        const tail = await getStepsAfter(runId, cursorRef.current);
        const known = stepsRef.current;
        if (tail.length > 0 && known) {
          const merged = mergeSteps(known, tail);
          setSteps(merged);
          cursorRef.current = settledBoundary(merged);
        }
      } catch {
        // Defensive: a transient poll failure keeps the last good timeline rather than crashing.
      }
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [connected, runId, steps === null]);

  if (error) {
    return (
      <div className="rounded-glass border border-line bg-surface/60 p-4">
        <p className="text-sm text-danger">{error}</p>
      </div>
    );
  }
  if (run === null || steps === null) {
    return <MonoLabel tone="faint">loading run</MonoLabel>;
  }

  const status = deriveRunStatus(steps);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 rounded-glass border border-line bg-surface/60 p-3">
        <MonoLabel tone="accent">run #{run.id}</MonoLabel>
        <Pill variant={status === 'failed' ? 'solid' : status === 'completed' ? 'green' : 'accent'}>
          {status}
        </Pill>
        {run.goal_summary ? (
          <span className="text-sm text-cream">{run.goal_summary}</span>
        ) : null}
        <span className="ml-auto inline-flex items-center gap-2">
          <StatusDot state={connected ? 'live' : 'error'} label={connected ? 'live' : 'offline'} />
          <MonoLabel tone="faint">{connected ? 'live' : 'offline'}</MonoLabel>
          <OverflowMenu
            label={`Run ${run.id} actions`}
            items={[
              { label: 'Refresh this run', onClick: () => void load() },
              { label: 'Reload all runs', onClick: onReloadRuns },
            ]}
          />
        </span>
      </div>

      {steps.length === 0 ? (
        <p className="text-sm text-muted">This run has no steps yet.</p>
      ) : (
        <ol className="space-y-3">
          {steps.map((step) => (
            <StepRow key={step.id} step={step} />
          ))}
        </ol>
      )}
    </div>
  );
}

// The runtime tab: the project's runs, newest first, with the selected run's live timeline.
export function RuntimeTab({ projectId }: { projectId: number }) {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);

  const loadRuns = useCallback(async () => {
    setError(null);
    try {
      const fetched = await listRuns(projectId);
      setRuns(fetched);
      setSelectedRunId((current) =>
        current && fetched.some((run) => run.id === current)
          ? current
          : (fetched[0]?.id ?? null),
      );
    } catch (err) {
      setError((err as Error).message);
      setRuns([]);
    }
  }, [projectId]);

  useEffect(() => {
    setRuns(null);
    setSelectedRunId(null);
    void loadRuns();
  }, [loadRuns]);

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (runs === null) return <MonoLabel tone="faint">loading runs</MonoLabel>;
  if (runs.length === 0) {
    return <p className="text-sm text-muted">No agent runs for this project yet.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {runs.map((run) => (
          <button
            key={run.id}
            type="button"
            onClick={() => setSelectedRunId(run.id)}
            className={`rounded-md border px-3 py-1 text-sm transition ${
              selectedRunId === run.id
                ? 'border-accent text-accent'
                : 'border-line text-muted hover:text-cream'
            }`}
          >
            <span className="font-mono text-xs">run #{run.id}</span>
            <span className="ml-2 text-xs">{run.status}</span>
          </button>
        ))}
      </div>

      {selectedRunId !== null ? (
        <RunTimeline runId={selectedRunId} onReloadRuns={() => void loadRuns()} />
      ) : null}
    </div>
  );
}
