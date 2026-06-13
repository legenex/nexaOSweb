import { useEffect, useState } from 'react';

import { MonoLabel, Pill, StatusDot } from '../../../components/primitives';
import type { DotState } from '../../../components/primitives';
import { getBuildLog } from './api';
import type { BuildLogEntry } from './api';

const STATUS_DOT: Record<string, DotState> = {
  applied: 'live',
  proposed: 'pending',
  rolled_back: 'warn',
};

// The build log stream from the Brain: build, applied edit, and rollback entries, newest
// first. The AI Editor writes an entry here on every applied change.
export function BuildLogTab({ projectId }: { projectId: number }) {
  const [entries, setEntries] = useState<BuildLogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setEntries(null);
    setError(null);
    getBuildLog(projectId)
      .then(setEntries)
      .catch((err: Error) => setError(err.message));
  }, [projectId]);

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!entries) return <MonoLabel tone="faint">loading build log</MonoLabel>;
  if (entries.length === 0) return <p className="text-sm text-muted">No build log entries yet.</p>;

  return (
    <ol className="space-y-3">
      {entries.map((entry) => (
        <li key={entry.id} className="rounded-glass border border-line bg-surface/60 p-4">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <StatusDot state={STATUS_DOT[entry.status] ?? 'pending'} label={entry.status} />
            <Pill variant="accent">{entry.action}</Pill>
            <Pill variant="grey">{entry.status}</Pill>
            {entry.file_path ? <MonoLabel tone="faint">{entry.file_path}</MonoLabel> : null}
            <span className="ml-auto">
              <MonoLabel tone="faint">{new Date(entry.created_at).toLocaleString()}</MonoLabel>
            </span>
          </div>
          <p className="text-sm text-cream">{entry.summary}</p>
          {entry.diff_summary ? (
            <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line bg-black/30 p-2 font-mono text-[0.7rem] text-muted">
              {entry.diff_summary}
            </pre>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
