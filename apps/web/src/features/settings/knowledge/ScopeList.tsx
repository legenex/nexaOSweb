import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../../app/client';
import { Button, MonoLabel, Pill } from '../../../components/primitives';
import { ConfidenceMeter, FieldShell, Provenance } from './parts';

type KnowledgeEntry = Schemas['KnowledgeEntryRead'];
type KnowledgeScope = 'general' | 'personal' | 'development';
type KnowledgeKind = 'fact' | 'preference' | 'pattern' | 'skill' | 'rule';

const KINDS: KnowledgeKind[] = ['fact', 'preference', 'pattern', 'skill', 'rule'];

const inputClass =
  'w-full rounded-md border border-line bg-canvas px-2 py-1 text-sm text-cream outline-none focus:border-accent';

function KindSelect({
  value,
  onChange,
}: {
  value: KnowledgeKind;
  onChange: (next: KnowledgeKind) => void;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value as KnowledgeKind)}
      className={inputClass}
    >
      {KINDS.map((kind) => (
        <option key={kind} value={kind}>
          {kind}
        </option>
      ))}
    </select>
  );
}

function EntryEditor({
  entry,
  onSaved,
  onCancel,
}: {
  entry: KnowledgeEntry;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [kind, setKind] = useState(entry.kind as KnowledgeKind);
  const [content, setContent] = useState(entry.content);
  const [confidence, setConfidence] = useState(entry.confidence);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!content.trim()) return;
    setBusy(true);
    try {
      const { error } = await api.PATCH('/knowledge/{entry_id}', {
        params: { path: { entry_id: entry.id } },
        body: { kind, content: content.trim(), confidence },
      });
      if (!error) onSaved();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-[1fr_auto] gap-3">
        <FieldShell label="kind">
          <KindSelect value={kind} onChange={setKind} />
        </FieldShell>
        <FieldShell label={`confidence ${Math.round(confidence * 100)}%`}>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={confidence}
            onChange={(event) => setConfidence(Number(event.target.value))}
            className="mt-2 w-40 accent-[color:var(--accent)]"
          />
        </FieldShell>
      </div>
      <FieldShell label="content">
        <textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          rows={3}
          className={inputClass}
        />
      </FieldShell>
      <div className="flex gap-2">
        <Button variant="primary" disabled={busy} onClick={() => void save()}>
          save
        </Button>
        <button
          type="button"
          onClick={onCancel}
          className="mono-label rounded-md border border-line px-3 py-1 hover:text-cream"
        >
          cancel
        </button>
      </div>
    </div>
  );
}

function EntryCard({
  entry,
  onChanged,
}: {
  entry: KnowledgeEntry;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const archived = entry.status === 'archived';

  const archive = async () => {
    setBusy(true);
    try {
      const { error } = await api.POST('/knowledge/{entry_id}/archive', {
        params: { path: { entry_id: entry.id } },
      });
      if (!error) onChanged();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={[
        'border-electric rounded-glass border border-line bg-surface/60 p-4',
        archived ? 'opacity-60' : '',
      ].join(' ')}
    >
      {editing ? (
        <EntryEditor
          entry={entry}
          onSaved={() => {
            setEditing(false);
            onChanged();
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Pill variant="accent">{entry.kind}</Pill>
            <Pill variant="grey">{entry.source}</Pill>
            {archived ? <Pill variant="grey">archived</Pill> : null}
            <span className="ml-auto">
              <ConfidenceMeter value={entry.confidence} />
            </span>
          </div>
          <p className="text-sm text-cream">{entry.content}</p>
          <Provenance data={entry.provenance as Record<string, unknown>} />
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent"
            >
              edit
            </button>
            {!archived ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void archive()}
                className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent disabled:opacity-60"
              >
                archive
              </button>
            ) : null}
          </div>
        </>
      )}
    </div>
  );
}

function AddEntry({ scope, onAdded }: { scope: KnowledgeScope; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<KnowledgeKind>('fact');
  const [content, setContent] = useState('');
  const [confidence, setConfidence] = useState(0.6);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!content.trim()) return;
    setBusy(true);
    try {
      const { error } = await api.POST('/knowledge', {
        body: { kind, scope, source: 'manual', content: content.trim(), confidence, status: 'active' },
      });
      if (!error) {
        setContent('');
        setKind('fact');
        setConfidence(0.6);
        setOpen(false);
        onAdded();
      }
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <Button variant="outline" onClick={() => setOpen(true)}>
        + add to {scope}
      </Button>
    );
  }

  return (
    <div className="space-y-3 rounded-glass border border-line bg-canvas/40 p-4">
      <div className="grid grid-cols-[1fr_auto] gap-3">
        <FieldShell label="kind">
          <KindSelect value={kind} onChange={setKind} />
        </FieldShell>
        <FieldShell label={`confidence ${Math.round(confidence * 100)}%`}>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={confidence}
            onChange={(event) => setConfidence(Number(event.target.value))}
            className="mt-2 w-40 accent-[color:var(--accent)]"
          />
        </FieldShell>
      </div>
      <FieldShell label="content">
        <textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          rows={3}
          placeholder={`Something the system knows in the ${scope} scope`}
          className={inputClass}
        />
      </FieldShell>
      <div className="flex gap-2">
        <Button variant="primary" disabled={busy} onClick={() => void submit()}>
          add entry
        </Button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="mono-label rounded-md border border-line px-3 py-1 hover:text-cream"
        >
          cancel
        </button>
      </div>
    </div>
  );
}

export function ScopeList({ scope }: { scope: KnowledgeScope }) {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error: err } = await api.GET('/knowledge', {
      params: { query: { scope } },
    });
    setLoading(false);
    if (err || !data) {
      setError('Could not load knowledge entries.');
      return;
    }
    setError(null);
    setEntries(data as KnowledgeEntry[]);
  }, [scope]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = entries.filter((entry) => showArchived || entry.status !== 'archived');
  const archivedCount = entries.filter((entry) => entry.status === 'archived').length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <AddEntry scope={scope} onAdded={() => void load()} />
        {archivedCount > 0 ? (
          <button
            type="button"
            onClick={() => setShowArchived((value) => !value)}
            className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent"
          >
            {showArchived ? 'hide archived' : `show archived (${archivedCount})`}
          </button>
        ) : null}
      </div>

      {loading ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : error ? (
        <p className="text-sm text-accent">{error}</p>
      ) : visible.length === 0 ? (
        <div className="rounded-glass border border-line bg-surface/40 p-6">
          <MonoLabel tone="faint">nothing here yet</MonoLabel>
          <p className="mt-2 text-sm text-muted">
            Add an entry by hand, or accept a Dreaming candidate into the {scope} scope.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {visible.map((entry) => (
            <EntryCard key={entry.id} entry={entry} onChanged={() => void load()} />
          ))}
        </div>
      )}
    </div>
  );
}
