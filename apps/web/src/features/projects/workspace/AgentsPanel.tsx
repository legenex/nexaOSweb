import { useEffect, useState } from 'react';

import { GlassCard, MonoLabel, Pill, StatusDot } from '../../../components/primitives';
import { deriveAgents, getRun, listRuns } from './runtimeApi';
import type { DerivedAgent } from './runtimeApi';

// How many recent runs to read steps from when deriving agents, so a long lived project does not
// fan out into an unbounded number of requests. If more runs exist, the panel says so.
const RUN_CAP = 25;

// The agents acting on this project, derived from the runtime ledger (never the build log). An
// agent is a distinct actor that authored steps, shown with its real tallies.
export function AgentsPanel({ projectId }: { projectId: number }) {
  const [agents, setAgents] = useState<DerivedAgent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [capped, setCapped] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setAgents(null);
    setError(null);
    setCapped(false);
    (async () => {
      try {
        const runs = await listRuns(projectId);
        if (cancelled) return;
        if (runs.length === 0) {
          setAgents([]);
          return;
        }
        const recent = runs.slice(0, RUN_CAP);
        const detailed = await Promise.all(recent.map((run) => getRun(run.id)));
        if (cancelled) return;
        const steps = detailed.flatMap((run) => run.steps);
        setAgents(deriveAgents(steps));
        setCapped(runs.length > RUN_CAP);
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return (
    <GlassCard>
      <div className="mb-3 flex items-center gap-2">
        <MonoLabel tone="accent">agents</MonoLabel>
        <MonoLabel tone="faint">derived from the runtime</MonoLabel>
      </div>

      {error ? (
        <p className="text-sm text-danger">{error}</p>
      ) : agents === null ? (
        <MonoLabel tone="faint">loading agents</MonoLabel>
      ) : agents.length === 0 ? (
        <p className="text-sm text-muted">
          No agent activity yet. Agents appear here once a run records steps.
        </p>
      ) : (
        <>
          <ul className="space-y-2">
            {agents.map((agent) => (
              <li
                key={agent.actor}
                className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface/60 p-3"
              >
                <StatusDot
                  state={agent.active > 0 ? 'current' : 'done'}
                  label={agent.active > 0 ? 'active' : 'idle'}
                />
                <span className="text-sm font-semibold text-cream">{agent.actor}</span>
                <MonoLabel tone="faint">
                  {agent.steps} step{agent.steps === 1 ? '' : 's'}
                </MonoLabel>
                <span className="ml-auto flex flex-wrap items-center gap-1">
                  {agent.verified > 0 ? (
                    <Pill variant="green">{agent.verified} verified</Pill>
                  ) : null}
                  {agent.unverified > 0 ? (
                    <Pill variant="grey">{agent.unverified} unverified</Pill>
                  ) : null}
                  {agent.failed > 0 ? <Pill variant="solid">{agent.failed} failed</Pill> : null}
                  {agent.active > 0 ? <Pill variant="accent">{agent.active} in flight</Pill> : null}
                </span>
              </li>
            ))}
          </ul>
          {capped ? (
            <p className="mt-2 text-xs text-muted">
              Showing agents across the {RUN_CAP} most recent runs.
            </p>
          ) : null}
        </>
      )}
    </GlassCard>
  );
}
