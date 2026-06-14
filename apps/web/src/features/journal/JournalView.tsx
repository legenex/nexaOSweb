import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { apiFetch } from '../../app/api';
import { Button, GlassCard, MonoLabel, Pill } from '../../components/primitives';
import { OverflowMenu } from '../../components/OverflowMenu';
import { ConfirmDialog } from '../projects/workspace/ConfirmDialog';

type JournalEntry = Schemas['JournalEntryRead'];
type Topic = Schemas['TopicRead'];
type Attachment = Schemas['AttachmentRead'];

// 'all' is the cross topic view; a number is a specific topic id.
type ActiveTab = number | 'all';

const inputClass =
  'w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent';

// Quick suggestions for the first few topics, offered only when they do not already exist.
// They are not phantom tabs: a tab appears once the user actually creates the topic.
const SUGGESTED_TOPICS = ['Personal', 'Work', 'Thoughts'];

// Friendly names for known inbound sources; anything else is title cased.
const SOURCE_NAMES: Record<string, string> = {
  whatsapp: 'WhatsApp',
  email: 'Email',
  sms: 'SMS',
  telegram: 'Telegram',
  imessage: 'iMessage',
};

function prettySource(slug: string): string {
  const key = slug.toLowerCase();
  return SOURCE_NAMES[key] ?? slug.charAt(0).toUpperCase() + slug.slice(1);
}

function parseTags(raw: string): string[] {
  return raw
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean);
}

// Inbound entries carry a source:<name> tag (see the Brain ingest route). Split those out so the
// origin shows as a distinct provenance pill, separate from the user's own tags.
function splitTags(tags: string[]): { sources: string[]; rest: string[] } {
  const sources: string[] = [];
  const rest: string[] = [];
  for (const tag of tags) {
    const match = /^source:(.+)$/i.exec(tag);
    if (match && match[1]) sources.push(match[1]);
    else rest.push(tag);
  }
  return { sources, rest };
}

// --- composer -------------------------------------------------------------------------------

function Composer({ topicId, onCreated }: { topicId: number | null; onCreated: () => void }) {
  const [body, setBody] = useState('');
  const [mood, setMood] = useState('');
  const [tags, setTags] = useState('');
  const [busy, setBusy] = useState(false);
  const [transcribed, setTranscribed] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [captureMsg, setCaptureMsg] = useState<string | null>(null);
  const pageInputRef = useRef<HTMLInputElement>(null);

  const submit = async () => {
    if (!body.trim()) return;
    setBusy(true);
    try {
      const { error } = await api.POST('/journal/entries', {
        body: {
          body: body.trim(),
          mood: mood.trim() || null,
          tags: parseTags(tags),
          topic_id: topicId,
        },
      });
      if (!error) {
        setBody('');
        setMood('');
        setTags('');
        setTranscribed(false);
        setCaptureMsg(null);
        onCreated();
      }
    } finally {
      setBusy(false);
    }
  };

  // Handwritten capture: photograph a page, send it to the vision capture endpoint, and drop the
  // transcription into the composer for the user to edit before saving. The image is never stored
  // (the Brain processes it in memory); only the text becomes an entry.
  const onPage = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setCapturing(true);
    setCaptureMsg(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const response = await apiFetch('/journal/capture', { method: 'POST', body: form });
      if (response.status === 501) {
        setCaptureMsg('Handwriting capture is not configured on this Brain yet.');
        return;
      }
      if (!response.ok) {
        setCaptureMsg('Could not read the page. Try a clearer, well lit photo.');
        return;
      }
      const data = (await response.json()) as { text?: string };
      const text = (data.text ?? '').trim();
      if (!text) {
        setCaptureMsg('No handwriting was detected in the photo.');
        return;
      }
      setBody(text);
      setTranscribed(true);
    } catch {
      setCaptureMsg('Could not reach the Brain to read the page. Check the connection.');
    } finally {
      setCapturing(false);
    }
  };

  return (
    <GlassCard className="border-electric">
      <div className="flex items-center justify-between gap-2">
        <MonoLabel tone="accent">new entry</MonoLabel>
        {transcribed ? <Pill variant="accent">transcribed</Pill> : null}
      </div>
      <textarea
        value={body}
        onChange={(event) => setBody(event.target.value)}
        rows={3}
        placeholder="What is on your mind?"
        className={`mt-2 resize-none ${inputClass}`}
      />
      {transcribed ? (
        <p className="mt-1 text-xs text-muted">Transcribed from a photo. Edit it before saving.</p>
      ) : null}
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
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={() => void submit()} disabled={!body.trim() || busy}>
          {busy ? 'saving' : 'Add entry'}
        </Button>
        <button
          type="button"
          onClick={() => pageInputRef.current?.click()}
          disabled={capturing}
          className="mono-label rounded-md border border-line px-3 py-2 hover:text-accent disabled:opacity-60"
        >
          {capturing ? 'reading page' : 'Photograph a page'}
        </button>
        <input
          ref={pageInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          hidden
          aria-hidden
          onChange={(event) => void onPage(event)}
        />
      </div>
      {captureMsg ? <p className="mt-2 text-xs text-danger">{captureMsg}</p> : null}
    </GlassCard>
  );
}

// --- attachments ----------------------------------------------------------------------------

// A single attachment thumbnail. Images uploaded this session show a real preview from a local
// object URL; anything loaded from the server (no content endpoint exists yet) shows an honest
// metadata tile rather than a broken image.
function AttachmentTile({
  att,
  previewUrl,
  onRemove,
}: {
  att: Attachment;
  previewUrl?: string;
  onRemove: () => void;
}) {
  const isImage = att.kind === 'image';
  return (
    <div
      className="group relative h-16 w-16 shrink-0 overflow-hidden rounded-md border border-line bg-canvas"
      title={att.original_name}
    >
      {isImage && previewUrl ? (
        <img src={previewUrl} alt={att.original_name} className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center px-1 text-center">
          <span className="mono-label text-accent">{isImage ? 'img' : 'file'}</span>
          <span className="mono-meta mt-1 block w-full truncate text-[0.5rem] text-faint">
            {att.original_name}
          </span>
        </div>
      )}
      <button
        type="button"
        aria-label={`Remove ${att.original_name}`}
        onClick={onRemove}
        className="absolute right-0 top-0 hidden h-5 w-5 items-center justify-center bg-canvas/80 text-xs text-danger group-hover:flex"
      >
        ×
      </button>
    </div>
  );
}

// --- entry editor ---------------------------------------------------------------------------

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
  const [tags, setTags] = useState(splitTags(entry.tags ?? []).rest.join(', '));
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!body.trim()) return;
    setBusy(true);
    try {
      // Preserve any source:* provenance tags the user does not edit in the plain tag field.
      const sources = splitTags(entry.tags ?? []).sources.map((s) => `source:${s}`);
      const { error } = await api.PATCH('/journal/entries/{entry_id}', {
        params: { path: { entry_id: entry.id } },
        body: {
          body: body.trim(),
          mood: mood.trim() || null,
          tags: [...parseTags(tags), ...sources],
        },
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

// --- entry card -----------------------------------------------------------------------------

type Pending = { type: 'entry' } | { type: 'attachment'; id: number; name: string };

function EntryCard({ entry, onChanged }: { entry: JournalEntry; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);

  const [attachments, setAttachments] = useState<Attachment[] | null>(null);
  const [attError, setAttError] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const previews = useRef<Map<number, string>>(new Map());

  const photoRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const { sources, rest } = useMemo(() => splitTags(entry.tags ?? []), [entry.tags]);

  const loadAttachments = useCallback(async () => {
    const { data, error } = await api.GET('/journal/entries/{entry_id}/attachments', {
      params: { path: { entry_id: entry.id } },
    });
    if (error || !data) {
      setAttError(true);
      return;
    }
    setAttError(false);
    setAttachments(data as Attachment[]);
  }, [entry.id]);

  useEffect(() => {
    void loadAttachments();
  }, [loadAttachments]);

  // Revoke any session object URLs when the card unmounts.
  useEffect(() => {
    const map = previews.current;
    return () => {
      for (const url of map.values()) URL.revokeObjectURL(url);
    };
  }, []);

  const upload = async (file: File, kind: 'image' | 'file') => {
    setUploadMsg(null);
    const form = new FormData();
    form.append('file', file);
    form.append('kind', kind);
    try {
      const response = await apiFetch(`/journal/entries/${entry.id}/attachments`, {
        method: 'POST',
        body: form,
      });
      if (!response.ok) {
        setUploadMsg('Could not attach that. Try again.');
        return;
      }
      const created = (await response.json()) as Attachment;
      if (kind === 'image') previews.current.set(created.id, URL.createObjectURL(file));
      await loadAttachments();
    } catch {
      setUploadMsg('Could not reach the Brain to attach. Check the connection.');
    }
  };

  const onPick = (kind: 'image' | 'file') => (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (file) void upload(file, kind);
  };

  const confirmDelete = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      if (pending.type === 'entry') {
        const { error } = await api.DELETE('/journal/entries/{entry_id}', {
          params: { path: { entry_id: entry.id } },
        });
        if (!error) onChanged();
      } else {
        const url = previews.current.get(pending.id);
        const { error } = await api.DELETE('/journal/attachments/{attachment_id}', {
          params: { path: { attachment_id: pending.id } },
        });
        if (!error) {
          if (url) {
            URL.revokeObjectURL(url);
            previews.current.delete(pending.id);
          }
          await loadAttachments();
        }
      }
    } finally {
      setBusy(false);
      setPending(null);
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
          <div className="mb-1 flex items-start justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="mono-meta text-faint">
                {new Date(entry.created_at).toLocaleString()}
              </span>
              {entry.mood ? <Pill variant="accent">{entry.mood}</Pill> : null}
              {sources.map((source) => (
                <Pill key={source} variant="green">
                  from {prettySource(source)}
                </Pill>
              ))}
            </div>
            <OverflowMenu
              label="Entry actions"
              items={[
                { label: 'Edit', onClick: () => setEditing(true) },
                { label: 'Attach photo', onClick: () => photoRef.current?.click() },
                { label: 'Attach file', onClick: () => fileRef.current?.click() },
                { label: 'Delete', danger: true, onClick: () => setPending({ type: 'entry' }) },
              ]}
            />
          </div>

          <p className="whitespace-pre-wrap text-sm text-cream">{entry.body}</p>

          {rest.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {rest.map((tag) => (
                <Pill key={tag} variant="grey">
                  {tag}
                </Pill>
              ))}
            </div>
          ) : null}

          {/* Attachments: thumbnails when present, an honest empty or error line otherwise. */}
          <div className="mt-3">
            {attError ? (
              <p className="mono-meta text-danger">Couldn't load attachments.</p>
            ) : attachments && attachments.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {attachments.map((att) => (
                  <AttachmentTile
                    key={att.id}
                    att={att}
                    previewUrl={previews.current.get(att.id)}
                    onRemove={() =>
                      setPending({ type: 'attachment', id: att.id, name: att.original_name })
                    }
                  />
                ))}
              </div>
            ) : attachments ? (
              <p className="mono-meta text-faint">No attachments yet.</p>
            ) : null}
            {uploadMsg ? <p className="mt-1 text-xs text-danger">{uploadMsg}</p> : null}
          </div>

          <input
            ref={photoRef}
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            aria-hidden
            onChange={onPick('image')}
          />
          <input ref={fileRef} type="file" hidden aria-hidden onChange={onPick('file')} />
        </>
      )}

      <ConfirmDialog
        open={pending !== null}
        title={pending?.type === 'attachment' ? 'Remove attachment' : 'Delete entry'}
        body={
          pending?.type === 'attachment'
            ? `Remove ${pending.name}? It is soft deleted and stays recoverable.`
            : 'Delete this entry? It is soft deleted and stays recoverable.'
        }
        confirmLabel={pending?.type === 'attachment' ? 'Remove' : 'Delete'}
        busy={busy}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPending(null)}
      />
    </GlassCard>
  );
}

// --- topics ---------------------------------------------------------------------------------

function TopicTabs({
  topics,
  active,
  onSelect,
}: {
  topics: Topic[];
  active: ActiveTab;
  onSelect: (tab: ActiveTab) => void;
}) {
  const tab = (key: ActiveTab, label: string) => {
    const isActive = key === active;
    return (
      <button
        key={String(key)}
        type="button"
        role="tab"
        aria-selected={isActive}
        onClick={() => onSelect(key)}
        className={[
          'rounded-md px-3 py-1.5 text-sm transition',
          isActive ? 'bg-accent text-canvas' : 'text-cream/80 hover:bg-white/5',
        ].join(' ')}
      >
        {label}
      </button>
    );
  };
  return (
    <div role="tablist" aria-label="Journal topics" className="flex flex-wrap gap-1">
      {tab('all', 'All')}
      {topics.map((topic) => tab(topic.id, topic.name))}
    </div>
  );
}

function CreateTopic({
  existing,
  onCreate,
}: {
  existing: Topic[];
  onCreate: (name: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  const suggestions = SUGGESTED_TOPICS.filter(
    (s) => !existing.some((t) => t.name.toLowerCase() === s.toLowerCase()),
  );

  const create = async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      await onCreate(trimmed);
      setName('');
      setOpen(false);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mono-label rounded-md border border-line px-3 py-1.5 hover:text-accent"
      >
        + topic
      </button>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        value={name}
        autoFocus
        onChange={(event) => setName(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') void create(name);
          if (event.key === 'Escape') setOpen(false);
        }}
        placeholder="new topic"
        className="w-40 rounded-md border border-line bg-canvas px-2 py-1 text-sm text-cream outline-none focus:border-accent"
      />
      <Button variant="primary" disabled={busy || !name.trim()} onClick={() => void create(name)}>
        add
      </Button>
      <button
        type="button"
        onClick={() => setOpen(false)}
        className="mono-label rounded-md border border-line px-2 py-1 hover:text-cream"
      >
        cancel
      </button>
      {suggestions.map((s) => (
        <button
          key={s}
          type="button"
          disabled={busy}
          onClick={() => void create(s)}
          className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent disabled:opacity-60"
        >
          {s}
        </button>
      ))}
    </div>
  );
}

// --- reflection -----------------------------------------------------------------------------

function Reflection({ entries }: { entries: JournalEntry[] }) {
  const moods = useMemo(
    () => [...new Set(entries.map((e) => e.mood).filter((m): m is string => Boolean(m)))].slice(0, 6),
    [entries],
  );
  return (
    <GlassCard className="border-electric">
      <MonoLabel tone="accent">reflection</MonoLabel>
      <p className="mt-2 text-sm text-muted">
        {entries.length} {entries.length === 1 ? 'entry' : 'entries'} in view.{' '}
        {moods.length > 0 ? `Recent moods: ${moods.join(', ')}.` : 'No moods recorded yet.'}
      </p>
      <p className="mt-2 text-xs text-faint">
        Entries consolidate into your Knowledge base on the nightly Dreaming run, surfaced for your
        approval in Settings, Knowledge, Dreaming. Nothing is written to Knowledge automatically.
      </p>
    </GlassCard>
  );
}

// --- view -----------------------------------------------------------------------------------

export function JournalView() {
  const [topics, setTopics] = useState<Topic[] | null>(null);
  const [topicError, setTopicError] = useState(false);
  const [active, setActive] = useState<ActiveTab>('all');

  const [entries, setEntries] = useState<JournalEntry[] | null>(null);
  const [entryError, setEntryError] = useState(false);

  const [pendingTopic, setPendingTopic] = useState<Topic | null>(null);
  const [topicBusy, setTopicBusy] = useState(false);

  const loadTopics = useCallback(async () => {
    const { data, error } = await api.GET('/journal/topics');
    if (error || !data) {
      setTopicError(true);
      return;
    }
    setTopicError(false);
    setTopics(data as Topic[]);
  }, []);

  const loadEntries = useCallback(async (tab: ActiveTab) => {
    const { data, error } =
      tab === 'all'
        ? await api.GET('/journal/entries')
        : await api.GET('/journal/entries', { params: { query: { topic_id: tab } } });
    if (error || !data) {
      setEntryError(true);
      setEntries(null);
      return;
    }
    setEntryError(false);
    setEntries(data as JournalEntry[]);
  }, []);

  useEffect(() => {
    void loadTopics();
  }, [loadTopics]);

  useEffect(() => {
    setEntries(null);
    void loadEntries(active);
  }, [active, loadEntries]);

  const createTopic = async (name: string) => {
    const { data, error } = await api.POST('/journal/topics', { body: { name } });
    if (!error && data) {
      await loadTopics();
      setActive((data as Topic).id);
    }
  };

  const confirmDeleteTopic = async () => {
    if (!pendingTopic) return;
    setTopicBusy(true);
    try {
      const wasActive = active === pendingTopic.id;
      const { error } = await api.DELETE('/journal/topics/{topic_id}', {
        params: { path: { topic_id: pendingTopic.id } },
      });
      if (!error) {
        if (wasActive) setActive('all');
        await loadTopics();
        await loadEntries(wasActive ? 'all' : active);
      }
    } finally {
      setTopicBusy(false);
      setPendingTopic(null);
    }
  };

  const activeTopic =
    typeof active === 'number' ? topics?.find((t) => t.id === active) ?? null : null;
  const composerTopicId = typeof active === 'number' ? active : null;

  return (
    <div className="space-y-5">
      {/* Topic tab bar with the create control and, for a real topic, its actions menu. */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
        <div className="flex flex-wrap items-center gap-2">
          {topicError ? (
            <p className="text-sm text-muted">Topics are unavailable.</p>
          ) : (
            <TopicTabs topics={topics ?? []} active={active} onSelect={setActive} />
          )}
          <CreateTopic existing={topics ?? []} onCreate={createTopic} />
        </div>
        {activeTopic ? (
          <OverflowMenu
            label={`Actions for ${activeTopic.name}`}
            items={[
              {
                label: 'Delete topic',
                danger: true,
                onClick: () => setPendingTopic(activeTopic),
              },
            ]}
          />
        ) : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="space-y-4">
          <Composer topicId={composerTopicId} onCreated={() => void loadEntries(active)} />

          {entryError ? (
            <p className="text-sm text-muted">
              The journal is unavailable. Check the Brain connection.
            </p>
          ) : entries === null ? (
            <p className="text-sm text-muted">Loading entries…</p>
          ) : entries.length === 0 ? (
            <GlassCard className="border-electric">
              <MonoLabel tone="faint">no entries yet</MonoLabel>
              <p className="mt-2 text-sm text-muted">
                {activeTopic
                  ? `Nothing under ${activeTopic.name} yet. Write an entry above, or photograph a handwritten page.`
                  : 'Write your first entry above, attach a photo or file, or photograph a handwritten page. Entries feed the nightly Dreaming consolidation.'}
              </p>
            </GlassCard>
          ) : (
            <div className="space-y-3">
              {entries.map((entry) => (
                <EntryCard key={entry.id} entry={entry} onChanged={() => void loadEntries(active)} />
              ))}
            </div>
          )}
        </div>

        <aside>
          <Reflection entries={entries ?? []} />
        </aside>
      </div>

      <ConfirmDialog
        open={pendingTopic !== null}
        title="Delete topic"
        body={
          pendingTopic
            ? `Delete the ${pendingTopic.name} topic? Its entries are kept and fall back to All.`
            : ''
        }
        confirmLabel="Delete topic"
        busy={topicBusy}
        onConfirm={() => void confirmDeleteTopic()}
        onCancel={() => setPendingTopic(null)}
      />
    </div>
  );
}
