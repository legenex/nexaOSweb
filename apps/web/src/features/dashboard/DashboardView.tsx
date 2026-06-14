import { useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { ApprovalQueue } from '../runtime/ApprovalQueue';
import { CommandRadar } from './CommandRadar';
import { DreamDigest } from './DreamDigest';
import { FocusStrip } from './FocusStrip';
import { MorningBrief } from './MorningBrief';

type DashboardSummary = Schemas['DashboardSummary'];

// The cockpit. Holographic backdrop and the dashboard HoloObject come from the shell; reduced
// motion is honoured globally. The summary is fetched once and shared by the Radar and the
// Focus strip, the brief and the dream digest fetch their own live state.
export function DashboardView() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    void (async () => {
      const { data, error: err } = await api.GET('/dashboard/summary');
      if (!active) return;
      if (err || !data) {
        setError(true);
        return;
      }
      setSummary(data as DashboardSummary);
    })();
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="space-y-6">
      <MorningBrief />

      <ApprovalQueue />

      {summary ? (
        <FocusStrip summary={summary} />
      ) : null}

      <DreamDigest />

      {error ? (
        <p className="text-sm text-muted">The Command Radar is unavailable. Check the Brain connection.</p>
      ) : summary ? (
        <CommandRadar summary={summary} />
      ) : (
        <p className="text-sm text-muted">Scanning local state…</p>
      )}
    </div>
  );
}
