import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../../app/client';
import { Button, MonoLabel, Pill } from '../../../components/primitives';
import { ConfidenceMeter } from './parts';

type MemoryCandidate = Schemas['MemoryCandidateRead'];
type DreamRun = Schemas['DreamRunRead'];

const inputClass =
  'w-full rounded-md border border-line bg-canvas px-2 py-1 text-sm text-cream outline-none focus:border-accent';

function sourceLabel(candidate: MemoryCandidate): string {
  const first = (candidate.source_refs ?? [])[0] as
    | { type?: string; title?: string }
    | undefined;
  if (!first) return 'unknown source';
  return [first.type, first.title].filter(Boolean).join(' · ') || 'unknown source';
}

function formatWhen(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function CandidateCard({
  candidate,
  busy,
  onAccept,
  onDismiss,
  onRefine,
}: {
  candidate: MemoryCandidate;
  busy: boolean;
  onAccept: () => void;
  onDismiss: () => void;
  onRefine: (content: string) => void;
}) {
  const [refining, setRefining] = useState(false);
  const [draft, setDraft] = useState(candidate.content);

  return (
    <div className="border-electric rounded-glass border border-line bg-surface/60 p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Pill variant="accent">{candidate.kind}</Pill>
        <Pill variant="grey">{candidate.scope}</Pill>
        <span className="ml-auto">
          <ConfidenceMeter value={candidate.confidence} />
        </span>
      </div>

      {refining ? (
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          rows={3}
          className={inputClass}
        />
      ) : (
        <p className="text-sm text-cream">{candidate.content}</p>
      )}

      <div className="mt-1 font-mono text-[0.62rem] text-faint">{sourceLabel(candidate)}</div>

      <div className="mt-3 flex flex-wrap gap-2">
        {refining ? (
          <>
            <Button
              variant="primary"
              disabled={busy || !draft.trim()}
              onClick={() => onRefine(draft.trim())}
            >
              save and accept
            </Button>
            <button
              type="button"
              onClick={() => {
                setDraft(candidate.content);
                setRefining(false);
              }}
              className="mono-label rounded-md border border-line px-3 py-1 hover:text-cream"
            >
              cancel
            </button>
          </>
        ) : (
          <>
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
            <button
              type="button"
              disabled={busy}
              onClick={() => setRefining(true)}
              className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent disabled:opacity-60"
            >
              refine
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function Group({
  title,
  candidates,
  busy,
  onAccept,
  onDismiss,
  onRefine,
}: {
  title: string;
  candidates: MemoryCandidate[];
  busy: boolean;
  onAccept: (id: number) => void;
  onDismiss: (id: number) => void;
  onRefine: (id: number, content: string) => void;
}) {
  return (
    <section>
      <MonoLabel tone="accent">{title}</MonoLabel>
      {candidates.length === 0 ? (
        <p className="mt-2 text-sm text-muted">No pending candidates.</p>
      ) : (
        <div className="mt-3 space-y-3">
          {candidates.map((candidate) => (
            <CandidateCard
              key={candidate.id}
              candidate={candidate}
              busy={busy}
              onAccept={() => onAccept(candidate.id)}
              onDismiss={() => onDismiss(candidate.id)}
              onRefine={(content) => onRefine(candidate.id, content)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export function DreamingReview({ onAccepted }: { onAccepted?: () => void }) {
  const [candidates, setCandidates] = useState<MemoryCandidate[]>([]);
  const [runs, setRuns] = useState<DreamRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const [candidatesRes, runsRes] = await Promise.all([
      api.GET('/dreaming/candidates', { params: { query: { status: 'pending' } } }),
      api.GET('/dreaming/runs'),
    ]);
    setLoading(false);
    if (candidatesRes.error || !candidatesRes.data) {
      setError('Could not load the review queue.');
      return;
    }
    setError(null);
    setCandidates(candidatesRes.data as MemoryCandidate[]);
    setRuns((runsRes.data as DreamRun[]) ?? []);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const runNow = useCallback(async () => {
    setBusy(true);
    try {
      await api.POST('/dreaming/run');
      await load();
    } finally {
      setBusy(false);
    }
  }, [load]);

  const accept = useCallback(
    async (id: number) => {
      setBusy(true);
      try {
        const { error: err } = await api.POST('/dreaming/candidates/{candidate_id}/accept', {
          params: { path: { candidate_id: id } },
        });
        if (!err) {
          onAccepted?.();
          await load();
        }
      } finally {
        setBusy(false);
      }
    },
    [load, onAccepted],
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

  // Refine accepts the candidate, then patches the resulting knowledge entry with the edited
  // content, so a refined memory lands in the Knowledge base with the user's wording.
  const refine = useCallback(
    async (id: number, content: string) => {
      setBusy(true);
      try {
        const { data, error: err } = await api.POST(
          '/dreaming/candidates/{candidate_id}/accept',
          { params: { path: { candidate_id: id } } },
        );
        if (!err && data) {
          await api.PATCH('/knowledge/{entry_id}', {
            params: { path: { entry_id: (data as Schemas['KnowledgeEntryRead']).id } },
            body: { content },
          });
          onAccepted?.();
          await load();
        }
      } finally {
        setBusy(false);
      }
    },
    [load, onAccepted],
  );

  const aboutYou = candidates.filter((candidate) => candidate.facet === 'about_user');
  const aboutItself = candidates.filter((candidate) => candidate.facet === 'about_self');

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <p className="max-w-prose text-sm text-muted">
          The human gate on memory. Accept a candidate to write it into the Knowledge base,
          dismiss to drop it, or refine to edit the wording before it lands.
        </p>
        <Button variant="outline" disabled={busy} onClick={() => void runNow()}>
          run now
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : error ? (
        <p className="text-sm text-accent">{error}</p>
      ) : (
        <>
          <Group
            title="about you"
            candidates={aboutYou}
            busy={busy}
            onAccept={(id) => void accept(id)}
            onDismiss={(id) => void dismiss(id)}
            onRefine={(id, content) => void refine(id, content)}
          />
          <Group
            title="about itself"
            candidates={aboutItself}
            busy={busy}
            onAccept={(id) => void accept(id)}
            onDismiss={(id) => void dismiss(id)}
            onRefine={(id, content) => void refine(id, content)}
          />
        </>
      )}

      <section>
        <MonoLabel tone="accent">run history</MonoLabel>
        {runs.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No runs yet.</p>
        ) : (
          <div className="mt-3 overflow-hidden rounded-glass border border-line">
            {runs.map((run) => (
              <div
                key={run.id}
                className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line/60 px-3 py-2 last:border-b-0"
              >
                <Pill variant={run.status === 'completed' ? 'green' : 'grey'}>{run.status}</Pill>
                <span className="font-mono text-xs text-muted">{run.trigger}</span>
                <span className="font-mono text-xs text-faint">
                  {run.candidates_created}/{run.items_considered} candidates
                </span>
                <span className="ml-auto font-mono text-xs text-faint">
                  {formatWhen(run.created_at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
