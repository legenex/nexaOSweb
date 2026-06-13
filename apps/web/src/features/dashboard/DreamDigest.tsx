import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { GlassCard, MonoLabel, Pill } from '../../components/primitives';
import { ConfidenceMeter } from './parts';

type MemoryCandidate = Schemas['MemoryCandidateRead'];

function sourceLabel(candidate: MemoryCandidate): string {
  const first = (candidate.source_refs ?? [])[0] as { type?: string; title?: string } | undefined;
  if (!first) return 'unknown source';
  return [first.type, first.title].filter(Boolean).join(' · ') || 'unknown source';
}

function CandidateRow({
  candidate,
  busy,
  onAccept,
  onDismiss,
}: {
  candidate: MemoryCandidate;
  busy: boolean;
  onAccept: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="rounded-md border border-line bg-canvas/40 p-3">
      <div className="mb-1.5 flex items-center gap-2">
        <Pill variant="accent">{candidate.kind}</Pill>
        <Pill variant="grey">{candidate.scope}</Pill>
        <span className="ml-auto">
          <ConfidenceMeter value={candidate.confidence} />
        </span>
      </div>
      <p className="text-sm text-cream">{candidate.content}</p>
      <div className="mt-1 font-mono text-[0.62rem] text-faint">{sourceLabel(candidate)}</div>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={onAccept}
          className="mono-label rounded-md border border-accent px-2 py-1 text-accent hover:bg-accent/10 disabled:opacity-60"
        >
          accept
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onDismiss}
          className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent disabled:opacity-60"
        >
          dismiss
        </button>
      </div>
    </div>
  );
}

function Stream({
  title,
  candidates,
  busy,
  onAccept,
  onDismiss,
}: {
  title: string;
  candidates: MemoryCandidate[];
  busy: boolean;
  onAccept: (id: number) => void;
  onDismiss: (id: number) => void;
}) {
  return (
    <div>
      <MonoLabel tone="accent">{title}</MonoLabel>
      {candidates.length === 0 ? (
        <p className="mt-2 text-sm text-muted">No pending candidates.</p>
      ) : (
        <div className="mt-2 space-y-2">
          {candidates.map((candidate) => (
            <CandidateRow
              key={candidate.id}
              candidate={candidate}
              busy={busy}
              onAccept={() => onAccept(candidate.id)}
              onDismiss={() => onDismiss(candidate.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function DreamDigest() {
  const [candidates, setCandidates] = useState<MemoryCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    const { data, error: err } = await api.GET('/dreaming/candidates', {
      params: { query: { status: 'pending' } },
    });
    setLoading(false);
    if (err || !data) {
      setError(true);
      return;
    }
    setCandidates(data as MemoryCandidate[]);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const accept = useCallback(
    async (id: number) => {
      setBusy(true);
      try {
        const { error: err } = await api.POST('/dreaming/candidates/{candidate_id}/accept', {
          params: { path: { candidate_id: id } },
        });
        if (!err) await load();
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  const dismiss = useCallback(
    async (id: number) => {
      setBusy(true);
      try {
        const { error: err } = await api.POST('/dreaming/candidates/{candidate_id}/dismiss', {
          params: { path: { candidate_id: id } },
        });
        if (!err) await load();
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  const aboutYou = candidates.filter((candidate) => candidate.facet === 'about_user');
  const aboutItself = candidates.filter((candidate) => candidate.facet === 'about_self');

  return (
    <GlassCard className="border-electric">
      <div className="mb-3 flex items-center justify-between">
        <MonoLabel tone="accent">dream digest</MonoLabel>
        <span className="mono-meta">the human gate on memory</span>
      </div>

      {loading ? (
        <p className="text-sm text-muted">Loading the queue…</p>
      ) : error ? (
        <p className="text-sm text-muted">The review queue is unavailable right now.</p>
      ) : candidates.length === 0 ? (
        <p className="text-sm text-muted">
          No candidates waiting. The nightly Dreaming run will surface new ones to review.
        </p>
      ) : (
        <div className="grid gap-5 md:grid-cols-2">
          <Stream
            title="about you"
            candidates={aboutYou}
            busy={busy}
            onAccept={(id) => void accept(id)}
            onDismiss={(id) => void dismiss(id)}
          />
          <Stream
            title="about itself"
            candidates={aboutItself}
            busy={busy}
            onAccept={(id) => void accept(id)}
            onDismiss={(id) => void dismiss(id)}
          />
        </div>
      )}
    </GlassCard>
  );
}
