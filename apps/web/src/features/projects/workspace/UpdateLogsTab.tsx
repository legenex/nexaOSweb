import { useEffect, useState } from 'react';

import { MonoLabel, Pill } from '../../../components/primitives';
import { getUpdates } from './api';
import type { ProjectUpdate } from './api';

// The project Update Log, newest first. Research findings posted by an attached research
// project arrive here with kind research_finding and are flagged as such.
export function UpdateLogsTab({ projectId }: { projectId: number }) {
  const [updates, setUpdates] = useState<ProjectUpdate[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setUpdates(null);
    setError(null);
    getUpdates(projectId)
      .then(setUpdates)
      .catch((err: Error) => setError(err.message));
  }, [projectId]);

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!updates) return <MonoLabel tone="faint">loading update logs</MonoLabel>;
  if (updates.length === 0) return <p className="text-sm text-muted">No updates yet.</p>;

  return (
    <ol className="space-y-3">
      {updates.map((update) => {
        const isResearch = update.kind === 'research_finding';
        return (
          <li key={update.id} className="rounded-glass border border-line bg-surface/60 p-4">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <Pill variant={isResearch ? 'green' : 'grey'}>
                {isResearch ? 'research finding' : update.kind}
              </Pill>
              <h4 className="text-sm font-semibold text-cream">{update.title}</h4>
              <span className="ml-auto">
                <MonoLabel tone="faint">{new Date(update.created_at).toLocaleString()}</MonoLabel>
              </span>
            </div>
            {update.body ? <p className="text-sm text-muted">{update.body}</p> : null}
          </li>
        );
      })}
    </ol>
  );
}
