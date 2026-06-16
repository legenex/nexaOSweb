import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import type { AutonomyLevel } from './levels';

export type ProjectAutonomyState = Schemas['ProjectAutonomyState'];

// Loads and mutates a project's autonomy default and kill switch through the AB4.3 Brain endpoints,
// so the Projects card, the Project Builder header, and the Send to agent control all read one
// consistent state. The provider key is never seen here: only the level and the kill switch flag.
export function useProjectAutonomy(projectId: number | null | undefined) {
  const [state, setState] = useState<ProjectAutonomyState | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (projectId == null) {
      setState(null);
      return;
    }
    setLoading(true);
    setError(null);
    const { data, error: err } = await api.GET('/agents/projects/{project_id}/autonomy', {
      params: { path: { project_id: projectId } },
    });
    setLoading(false);
    if (err || !data) {
      setError('Could not load autonomy.');
      return;
    }
    setState(data as ProjectAutonomyState);
  }, [projectId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const setDefault = useCallback(
    async (level: AutonomyLevel) => {
      if (projectId == null) return;
      setBusy(true);
      setError(null);
      const { data, error: err } = await api.PUT('/agents/projects/{project_id}/autonomy', {
        params: { path: { project_id: projectId } },
        body: { default_level: level },
      });
      setBusy(false);
      if (err || !data) {
        setError('Could not update the autonomy default.');
        return;
      }
      setState(data as ProjectAutonomyState);
    },
    [projectId],
  );

  const setKill = useCallback(
    async (engaged: boolean) => {
      if (projectId == null) return;
      setBusy(true);
      setError(null);
      const { data, error: err } = await api.POST('/agents/projects/{project_id}/kill-switch', {
        params: { path: { project_id: projectId } },
        body: { engaged },
      });
      setBusy(false);
      if (err || !data) {
        setError('Could not toggle the kill switch.');
        return;
      }
      setState(data as ProjectAutonomyState);
    },
    [projectId],
  );

  return { state, loading, busy, error, reload, setDefault, setKill };
}
