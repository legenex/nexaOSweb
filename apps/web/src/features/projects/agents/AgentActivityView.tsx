import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';

import { MonoLabel, Pill, StatusDot } from '../../../components/primitives';
import type { DotState } from '../../../components/primitives';
import { RunTimeline } from '../workspace/RunTimeline';
import {
  ACTIVITY_RUN_CAP,
  formatCost,
  formatDuration,
  formatTokens,
  loadAgentActivity,
} from './agentActivity';
import type { AgentRunRow, GateDecision } from './agentActivity';

// Run status mapped to the shared status dot. Status colours are status only: the brand orange is
// never borrowed to mean a status it does not own.
const RUN_DOT: Record<string, DotState> = {
  planned: 'pending',
  executing: 'current',
  waiting_approval: 'gate',
  blocked: 'warn',
  failed: 'error',
  completed: 'done',
  completed_verified: 'live',
};

const GATE_DOT: Record<GateDecision, DotState> = {
  awaiting: 'gate',
  approved: 'done',
  rejected: 'error',
  autonomous: 'current',
  gated: 'pending',
};

const GATE_LABEL: Record<GateDecision, string> = {
  awaiting: 'awaiting gate',
  approved: 'approved',
  rejected: 'rejected',
  autonomous: 'no gate',
  gated: 'gated',
};

function Cell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <MonoLabel tone="faint" className="mb-1 block text-[0.55rem]">
        {label}
      </MonoLabel>
      {children}
    </div>
  );
}

function RunRow({ row, onOpen }: { row: AgentRunRow; onOpen: () => void }) {
  const startedAt = new Date(row.createdAt).toLocaleString();
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Open run ${row.runId}: ${row.task}, ${row.status.replace(/_/g, ' ')}`}
        className="block w-full rounded-glass border border-line bg-surface/60 p-4 text-left outline-none transition hover:border-accent focus-visible:ring-1 focus-visible:ring-accent"
      >
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <MonoLabel tone="accent">run #{row.runId}</MonoLabel>
          <Pill variant="grey">{row.projectName}</Pill>
          <span className="truncate text-sm font-semibold text-cream">{row.task}</span>
          <span className="ml-auto inline-flex items-center gap-2">
            <StatusDot state={RUN_DOT[row.status] ?? 'pending'} label={row.status} />
            <span className="text-sm text-cream">{row.status.replace(/_/g, ' ')}</span>
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Cell label="backend">
            <Pill variant="accent">{row.backend}</Pill>
          </Cell>
          <Cell label="autonomy">
            <span className="text-sm text-cream">
              L{row.autonomy.level}
              <span className="ml-1 text-muted">{row.autonomy.mode}</span>
            </span>
          </Cell>
          <Cell label="gate">
            <span className="inline-flex items-center gap-1">
              <StatusDot state={GATE_DOT[row.gate]} label={GATE_LABEL[row.gate]} />
              <span className="text-sm text-cream">{GATE_LABEL[row.gate]}</span>
            </span>
          </Cell>
          <Cell label="tokens">
            <span className="text-sm text-cream">{formatTokens(row.usage.tokens)}</span>
          </Cell>
          <Cell label="cost">
            <span className="text-sm text-cream">{formatCost(row.usage.costUsd)}</span>
          </Cell>
          <Cell label="timing">
            <span className="text-sm text-cream">{formatDuration(row.durationMs)}</span>
            <MonoLabel tone="faint" className="mt-1 block text-[0.55rem]">
              {row.stepCount} step{row.stepCount === 1 ? '' : 's'} · {startedAt}
            </MonoLabel>
          </Cell>
        </div>
      </button>
    </li>
  );
}

// The agent activity surface: recent build runs across every project, each row carrying the
// observability dimensions and opening the existing run detail with its diff, transcript, and
// reasoning. Read only; it never writes the runtime.
export function AgentActivityView() {
  const [rows, setRows] = useState<AgentRunRow[] | null>(null);
  const [capped, setCapped] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openRunId, setOpenRunId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    (async () => {
      try {
        const activity = await loadAgentActivity();
        if (cancelled) return;
        setRows(activity.rows);
        setCapped(activity.capped);
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (openRunId !== null) {
    return (
      <section className="space-y-4">
        <button
          type="button"
          onClick={() => setOpenRunId(null)}
          className="mono-label rounded-md border border-line px-3 py-1 hover:text-accent"
        >
          ← agent activity
        </button>
        <RunTimeline runId={openRunId} />
      </section>
    );
  }

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (rows === null) return <MonoLabel tone="faint">loading agent activity</MonoLabel>;
  if (rows.length === 0) {
    return (
      <section className="rounded-glass border border-line bg-surface/60 p-6">
        <MonoLabel tone="faint">no agent runs yet</MonoLabel>
        <p className="mt-2 text-sm text-muted">
          Approve a project shaped item through Project Builder to start a build run. Its runs
          appear here as the agents work.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-3">
      <ul className="space-y-3">
        {rows.map((row) => (
          <RunRow key={row.runId} row={row} onOpen={() => setOpenRunId(row.runId)} />
        ))}
      </ul>
      {capped ? (
        <p className="text-xs text-muted">
          Showing the {ACTIVITY_RUN_CAP} most recent runs across all projects.
        </p>
      ) : null}
    </section>
  );
}
