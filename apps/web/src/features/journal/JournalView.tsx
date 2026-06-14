import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { Button, GlassCard, MonoLabel, Pill } from '../../components/primitives';

type JournalEntry = Schemas['JournalEntryRead'];

const inputClass =
  'w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent';

function parseTags(raw: string): string[] {
  return raw
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function Composer({ onCreated }: { onCreated: () => void }) {
  const [body, setBody] = useState('');
  const [mood, setMood] = useState('');
  const [tags, setTags] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!body.trim()) return;
    setBusy(true);
    try {
      const { error } = await api.POST('/journal/entries', {
        body: { body: body.trim(), mood: mood.trim() || null, tags: parseTags(tags) },
      });
      if (!error) {
        setBody('');
        setMood('');
        setTags('');
        onCreated();
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <GlassCard className="border-electric">
      <MonoLabel tone="accent">new entry</MonoLabel>
      <textarea
        value={body}
        onChange={(event) => setBody(event.target.value)}
        rows={3}
        placeholder="What is on your mind?"
        className={`mt-2 resize-none ${inputClass}`}
      />
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <input
          value={mood}
          onChange={(event) => setMood(event.target.value)}
          placeholder="mood (optional)"
          className={inputClass}
        />
        <input
          value={tags}
          onChange={(event) => setTags(event.target.value)}
          placeholder="tags, comma separated"
          className={inputClass}
        />
      </div>
      <div className="mt-3">
        <Button variant="primary" onClick={() => void submit()} disabled={!body.trim() || busy}>
          {busy ? 'saving' : 'Add entry'}
        </Button>
      </div>
    </GlassCard>
  );
}

function EntryEditor({
  entry,
  onSaved,
  onCancel,
}: {
  entry: JournalEntry;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [body, setBody] = useState(entry.body);
  const [mood, setMood] = useState(entry.mood ?? '');
  const [tags, setTags] = useState((entry.tags ?? []).join(', '));
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!body.trim()) return;
    setBusy(true);
    try {
      const { error } = await api.PATCH('/journal/entries/{entry_id}', {
        params: { path: { entry_id: entry.id } },
        body: { body: body.trim(), mood: mood.trim() || null, tags: parseTags(tags) },
      });
      if (!error) onSaved();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <textarea
        value={body}
        onChange={(event) => setBody(event.target.value)}
        rows={3}
        className={`resize-none ${inputClass}`}
      />
      <div className="grid gap-2 sm:grid-cols-2">
        <input value={mood} onChange={(e) => setMood(e.target.value)} placeholder="mood" className={inputClass} />
        <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="tags" className={inputClass} />
      </div>
      <div className="flex gap-2">
        <Button variant="primary" onClick={() => void save()} disabled={busy}>
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

function EntryCard({ entry, onChanged }: { entry: JournalEntry; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  const remove = async () => {
    setBusy(true);
    try {
      const { error } = await api.DELETE('/journal/entries/{entry_id}', {
        params: { path: { entry_id: entry.id } },
      });
      if (!error) onChanged();
    } finally {
      setBusy(false);
    }
  };

  return (
    <GlassCard className="border-electric">
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
          <div className="mb-1 flex items-center gap-2">
            <span className="mono-meta text-faint">{new Date(entry.created_at).toLocaleString()}</span>
            {entry.mood ? <Pill variant="accent">{entry.mood}</Pill> : null}
          </div>
          <p className="whitespace-pre-wrap text-sm text-cream">{entry.body}</p>
          {entry.tags.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {entry.tags.map((tag) => (
                <Pill key={tag} variant="grey">
                  {tag}
                </Pill>
              ))}
            </div>
          ) : null}
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent"
            >
              edit
            </button>
            {confirming ? (
              <>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void remove()}
                  className="mono-label rounded-md border border-danger px-2 py-1 text-danger hover:bg-danger/10 disabled:opacity-60"
                >
                  confirm delete
                </button>
                <button
                  type="button"
                  onClick={() => setConfirming(false)}
                  className="mono-label rounded-md border border-line px-2 py-1 hover:text-cream"
                >
                  cancel
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => setConfirming(true)}
                className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent"
              >
                delete
              </button>
            )}
          </div>
        </>
      )}
    </GlassCard>
  );
}

function Reflection({ entries }: { entries: JournalEntry[] }) {
  const moods = useMemo(
    () => [...new Set(entries.map((e) => e.mood).filter((m): m is string => Boolean(m)))].slice(0, 6),
    [entries],
  );
  return (
    <GlassCard className="border-electric">
      <MonoLabel tone="accent">reflection</MonoLabel>
      <p className="mt-2 text-sm text-muted">
        {entries.length} {entries.length === 1 ? 'entry' : 'entries'}.{' '}
        {moods.length > 0 ? `Recent moods: ${moods.join(', ')}.` : 'No moods recorded yet.'}
      </p>
      <p className="mt-2 text-xs text-faint">
        Entries consolidate into your Knowledge base on the nightly Dreaming run, surfaced for your
        approval in Settings, Knowledge, Dreaming. Nothing is written to Knowledge automatically.
      </p>
    </GlassCard>
  );
}

export function JournalView() {
  const [entries, setEntries] = useState<JournalEntry[] | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    const { data, error: err } = await api.GET('/journal/entries');
    if (err || !data) {
      setError(true);
      return;
    }
    setError(false);
    setEntries(data as JournalEntry[]);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <div className="space-y-4">
        <Composer onCreated={() => void load()} />
        {error ? (
          <p className="text-sm text-muted">The journal is unavailable. Check the Brain connection.</p>
        ) : entries === null ? (
          <p className="text-sm text-muted">Loading entries…</p>
        ) : entries.length === 0 ? (
          <GlassCard className="border-electric">
            <MonoLabel tone="faint">no entries yet</MonoLabel>
            <p className="mt-2 text-sm text-muted">
              Write your first entry above. Entries are yours to edit and delete, and they feed the
              nightly Dreaming consolidation.
            </p>
          </GlassCard>
        ) : (
          <div className="space-y-3">
            {entries.map((entry) => (
              <EntryCard key={entry.id} entry={entry} onChanged={() => void load()} />
            ))}
          </div>
        )}
      </div>

      <aside>
        <Reflection entries={entries ?? []} />
      </aside>
    </div>
  );
}
