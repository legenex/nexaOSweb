import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { Button } from '../../components/primitives';
import { MonoLabel } from '../../components/primitives';

type ModelsConfig = Schemas['ModelsConfig'];
type ModelEntry = Schemas['ModelEntry'];
type AgentBinding = Schemas['AgentBinding'];

// A cost hint badge. Colour stays inside the brand: accent for the priciest tier, muted
// otherwise, all from CSS variables.
function CostBadge({ cost }: { cost: ModelEntry['cost'] }) {
  const perM = cost.blended_per_mtok;
  const title = perM != null ? `~ $${perM} per million tokens (hint)` : 'cost unknown';
  return (
    <span
      title={title}
      className={[
        'rounded-md border px-2 py-0.5 font-mono text-xs',
        cost.tier === 'high'
          ? 'border-accent/60 text-accent'
          : 'border-line text-muted',
      ].join(' ')}
    >
      {cost.label}
      {perM != null ? <span className="ml-1 opacity-70">{`$${perM}/M`}</span> : null}
    </span>
  );
}

function KeyRow({
  entry,
  onRemap,
  busy,
}: {
  entry: ModelEntry;
  onRemap: (key: string, model: string) => Promise<void>;
  busy: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(entry.model);

  useEffect(() => {
    setValue(entry.model);
  }, [entry.model]);

  const save = async () => {
    const next = value.trim();
    if (!next || next === entry.model) {
      setEditing(false);
      return;
    }
    await onRemap(entry.key, next);
    setEditing(false);
  };

  return (
    <div className="flex items-center gap-3 border-b border-line/60 py-3 last:border-b-0">
      <div className="w-44 shrink-0">
        <span className="font-mono text-sm text-cream">{entry.key}</span>
      </div>
      <div className="flex-1">
        {editing ? (
          <input
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="provider/model-id"
            spellCheck={false}
            className="w-full rounded-md border border-line bg-canvas px-2 py-1 font-mono text-sm text-cream outline-none focus:border-accent"
          />
        ) : (
          <span className="font-mono text-sm text-muted">{entry.model}</span>
        )}
      </div>
      <CostBadge cost={entry.cost} />
      <div className="w-28 shrink-0 text-right">
        {editing ? (
          <div className="flex justify-end gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => void save()}
              className="mono-label rounded-md border border-accent px-2 py-1 text-accent hover:bg-accent/10 disabled:opacity-60"
            >
              save
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="mono-label rounded-md border border-line px-2 py-1 hover:text-cream"
            >
              cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent"
          >
            remap
          </button>
        )}
      </div>
    </div>
  );
}

function AddKeyForm({
  onAdd,
  busy,
}: {
  onAdd: (key: string, model: string) => Promise<void>;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState('');
  const [model, setModel] = useState('');

  const submit = async () => {
    if (!key.trim() || !model.trim()) return;
    await onAdd(key.trim(), model.trim());
    setKey('');
    setModel('');
    setOpen(false);
  };

  if (!open) {
    return (
      <Button variant="outline" className="mt-4" onClick={() => setOpen(true)}>
        + add model key
      </Button>
    );
  }

  return (
    <div className="mt-4 flex flex-wrap items-center gap-2 rounded-md border border-line bg-canvas/60 p-3">
      <input
        value={key}
        onChange={(event) => setKey(event.target.value)}
        placeholder="semantic_key"
        spellCheck={false}
        className="w-44 rounded-md border border-line bg-canvas px-2 py-1 font-mono text-sm text-cream outline-none focus:border-accent"
      />
      <input
        value={model}
        onChange={(event) => setModel(event.target.value)}
        placeholder="provider/model-id"
        spellCheck={false}
        className="flex-1 rounded-md border border-line bg-canvas px-2 py-1 font-mono text-sm text-cream outline-none focus:border-accent"
      />
      <Button variant="primary" disabled={busy} onClick={() => void submit()}>
        add
      </Button>
      <button
        type="button"
        onClick={() => setOpen(false)}
        className="mono-label rounded-md border border-line px-2 py-1 hover:text-cream"
      >
        cancel
      </button>
    </div>
  );
}

function AgentList({ agents }: { agents: AgentBinding[] }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {agents.map((agent) => (
        <div key={agent.id} className="rounded-md border border-line bg-canvas/40 p-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-cream">{agent.label}</span>
            <span className="font-mono text-xs text-accent">{agent.model_key}</span>
          </div>
          <p className="mt-1 text-xs text-muted">{agent.description}</p>
          <p className="mt-2 font-mono text-xs text-muted/80">
            {agent.resolved_model ?? 'key not found'}
          </p>
        </div>
      ))}
    </div>
  );
}

export function ModelsAgentsPanel() {
  const [config, setConfig] = useState<ModelsConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const { data, error: err } = await api.GET('/settings/models');
    if (err || !data) {
      setError('Could not load the model registry.');
      return;
    }
    setError(null);
    setConfig(data as ModelsConfig);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const remap = useCallback(
    async (key: string, model: string) => {
      setBusy(true);
      setError(null);
      try {
        const { error: err } = await api.PATCH('/settings/models/keys/{key}', {
          params: { path: { key } },
          body: { model },
        });
        if (err) {
          setError(`Remap rejected. Check the model id format (provider/model-id).`);
          return;
        }
        await load();
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  const addKey = useCallback(
    async (key: string, model: string) => {
      setBusy(true);
      setError(null);
      try {
        const { error: err } = await api.POST('/settings/models/keys', {
          body: { key, model },
        });
        if (err) {
          setError('Could not add the key. It may already exist or the id is invalid.');
          return;
        }
        await load();
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  if (!config) {
    return (
      <p className="text-sm text-muted">{error ?? 'Loading the model registry…'}</p>
    );
  }

  return (
    <div className="space-y-8">
      <section>
        <MonoLabel tone="accent">semantic keys</MonoLabel>
        <p className="mt-2 mb-3 max-w-prose text-sm text-muted">
          Business logic calls a key, never a model id. Remap a key here and the router
          picks it up at once. The cost badge is a rough per million token hint.
        </p>
        <div className="rounded-glass border border-line bg-canvas/30 px-4">
          {config.keys.map((entry) => (
            <KeyRow key={entry.key} entry={entry} onRemap={remap} busy={busy} />
          ))}
        </div>
        <AddKeyForm onAdd={addKey} busy={busy} />
      </section>

      <section>
        <MonoLabel tone="accent">agents</MonoLabel>
        <p className="mt-2 mb-3 max-w-prose text-sm text-muted">
          Each agent runs through a semantic key, so a remap above changes the model an
          agent uses without any code change.
        </p>
        <AgentList agents={config.agents} />
      </section>

      {error ? <p className="text-sm text-accent">{error}</p> : null}
    </div>
  );
}
