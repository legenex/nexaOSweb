import { useCallback, useEffect, useState } from 'react';

import { MonoLabel } from '../../../components/primitives';
import { RunTimeline } from './RunTimeline';
import { listRuns } from './runtimeApi';
import type { Run } from './runtimeApi';

// The runtime tab: the project's runs, newest first, with the selected run's live detail. The
// detail carries the orchestration walk and every step's diff, transcript, and reasoning.
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
