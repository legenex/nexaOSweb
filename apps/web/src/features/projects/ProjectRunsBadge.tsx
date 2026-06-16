import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { StatusDot } from '../../components/primitives';
import type { DotState } from '../../components/primitives';

type Run = Schemas['RunRead'];

// A small live badge of the project's agent build runs, streamed into the Projects view so an
// in-flight run is visible without opening the workspace. It reads the runtime run list (a build
// run is one with a non-null backend) and polls while any run is still active.
export function ProjectRunsBadge({ projectId }: { projectId: number }) {
  const [runs, setRuns] = useState<Run[]>([]);

  const load = useCallback(async () => {
    const { data } = await api.GET('/runtime/runs', {
      params: { query: { project_id: projectId, active: true } },
    });
    const all = (data as Run[]) ?? [];
    setRuns(all.filter((run) => run.backend != null));
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    void load();
    const id = window.setInterval(() => {
      if (!cancelled) void load();
    }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [load]);

  if (runs.length === 0) return null;

  const awaiting = runs.filter((run) => run.status === 'waiting_approval').length;
  const running = runs.length - awaiting;
  const dot: DotState = awaiting > 0 ? 'gate' : 'live';
  const text =
    awaiting > 0
      ? `${awaiting} run${awaiting > 1 ? 's' : ''} awaiting review`
      : `${running} run${running > 1 ? 's' : ''} building`;

  return (
    <span className="mt-3 inline-flex items-center gap-2" onClick={(event) => event.stopPropagation()}>
      <StatusDot state={dot} label={text} />
      <span className="mono-meta text-muted">{text}</span>
    </span>
  );
}
