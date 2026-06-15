import { useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { ApprovalQueue } from '../runtime/ApprovalQueue';
import { FailureView } from '../runtime/FailureView';
import { AISystems } from './AISystems';
import { CommandRadar } from './CommandRadar';
import { DreamDigest } from './DreamDigest';
import { FocusStrip } from './FocusStrip';
import { MorningBrief } from './MorningBrief';
import { PulseBar } from './PulseBar';

type DashboardSummary = Schemas['DashboardSummary'];

// The cockpit. Holographic backdrop and the dashboard HoloObject come from the shell; reduced
// motion is honoured globally. The layout reads top to bottom: a pinned pulse bar of headline
// state, the time aware brief, then a two column body that pairs AI insights and the dream
// digest with an AI systems rail (connections and agents). The live pipeline and the runtime
// queues sit below. The summary is fetched once and shared by the pulse bar, the insights
// strip, the pipeline, and the model usage in the rail.
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
      {error ? (
        <p className="text-sm text-muted">
          The cockpit is unavailable. Check the Brain connection.
        </p>
      ) : summary ? (
        <PulseBar summary={summary} />
      ) : (
        <p className="text-sm text-muted">Scanning local state…</p>
      )}

      <MorningBrief />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {summary ? <FocusStrip summary={summary} /> : null}
          <DreamDigest />
        </div>
        <AISystems usage={summary?.model_usage ?? []} />
      </div>

      {summary ? <CommandRadar summary={summary} /> : null}

      <ApprovalQueue />

      <FailureView />
    </div>
  );
}
