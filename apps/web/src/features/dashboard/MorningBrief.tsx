import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { GlassCard, MonoLabel, Pill } from '../../components/primitives';

type DashboardBrief = Schemas['DashboardBrief'];
type BriefMode = 'morning' | 'afternoon' | 'evening';

const BRIEF_MODES: BriefMode[] = ['morning', 'afternoon', 'evening'];

function formatWhen(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

export function MorningBrief() {
  const [brief, setBrief] = useState<DashboardBrief | null>(null);
  const [mode, setMode] = useState<BriefMode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const fetchBrief = useCallback(async (which?: BriefMode, refresh?: boolean) => {
    setLoading(true);
    setError(false);
    const { data, error: err } = await api.GET('/dashboard/brief', {
      params: {
        query: {
          ...(which ? { mode: which } : {}),
          ...(refresh ? { refresh: true } : {}),
        },
      },
    });
    setLoading(false);
    if (err || !data) {
      setError(true);
      return;
    }
    const result = data as DashboardBrief;
    setBrief(result);
    setMode(result.mode as BriefMode);
  }, []);

  useEffect(() => {
    // Let the Brain pick the mode from the time of day on first load.
    void fetchBrief();
  }, [fetchBrief]);

  const switchMode = (which: BriefMode) => {
    setMode(which);
    void fetchBrief(which);
  };

  const hasText = Boolean(brief && brief.text.trim());

  return (
    <GlassCard className="border-electric">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <MonoLabel tone="accent">{`${mode ?? 'morning'} brief`}</MonoLabel>
          {brief ? <Pill variant="grey">{brief.date}</Pill> : null}
        </div>
        <div className="flex items-center gap-1">
          {BRIEF_MODES.map((which) => (
            <button
              key={which}
              type="button"
              onClick={() => switchMode(which)}
              aria-pressed={mode === which}
              className={[
                'mono-label rounded-md px-2 py-1 transition',
                mode === which ? 'bg-accent text-canvas' : 'border border-line hover:text-accent',
              ].join(' ')}
            >
              {which}
            </button>
          ))}
          <button
            type="button"
            onClick={() => void fetchBrief(mode ?? undefined, true)}
            disabled={loading}
            className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent disabled:opacity-60"
          >
            refresh
          </button>
        </div>
      </div>

      {loading && !brief ? (
        <p className="text-sm text-muted">Reading the day…</p>
      ) : error ? (
        <p className="text-sm text-muted">
          The brief is unavailable. Check the Brain connection and refresh.
        </p>
      ) : hasText ? (
        <p className="max-w-prose text-[15px] leading-relaxed text-cream">{brief!.text}</p>
      ) : (
        <p className="text-sm text-muted">
          Nothing to brief yet. Capture an idea or run Dreaming, then refresh.
        </p>
      )}

      {brief && hasText ? (
        <div className="mono-meta mt-3">generated {formatWhen(brief.generated_at)}</div>
      ) : null}
    </GlassCard>
  );
}
