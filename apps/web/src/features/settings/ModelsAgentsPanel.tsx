import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { useAuth } from '../../app/AuthProvider';
import { Button, MonoLabel, StatusDot } from '../../components/primitives';
import { ConfirmDialog } from '../projects/workspace/ConfirmDialog';

type ModelsConfig = Schemas['ModelsConfig'];
type ModelEntry = Schemas['ModelEntry'];
type AgentBinding = Schemas['AgentBinding'];
type ProviderStatus = Schemas['ProviderStatus'];
type DiscoveredModel = Schemas['DiscoveredModelRead'];

const INPUT =
  'rounded-md border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent';

// The providers we present a row for, with the one click deep link to each key page. The Brain
// resolves keys for anthropic, openai, and gemini and discovers their model lists; tavily is key
// only with no model list. Slugs match what the Brain reports and accepts on connect.
type ProviderMeta = {
  slug: string;
  label: string;
  keyUrl: string;
  hasModels: boolean;
};

const PROVIDERS: ProviderMeta[] = [
  {
    slug: 'anthropic',
    label: 'Anthropic',
    keyUrl: 'https://console.anthropic.com/settings/keys',
    hasModels: true,
  },
  {
    slug: 'openai',
    label: 'OpenAI',
    keyUrl: 'https://platform.openai.com/api-keys',
    hasModels: true,
  },
  {
    slug: 'gemini',
    label: 'Gemini',
    keyUrl: 'https://aistudio.google.com/apikey',
    hasModels: true,
  },
  {
    slug: 'tavily',
    label: 'Tavily',
    keyUrl: 'https://app.tavily.com/home',
    hasModels: false,
  },
];

function metaFor(slug: string): ProviderMeta {
  return (
    PROVIDERS.find((p) => p.slug === slug) ?? {
      slug,
      label: slug.charAt(0).toUpperCase() + slug.slice(1),
      keyUrl: '',
      hasModels: true,
    }
  );
}

// The provider prefix of a concrete model id, for example anthropic from anthropic/claude-sonnet-4-6.
function providerOf(model: string): string {
  const slash = model.indexOf('/');
  return slash > 0 ? model.slice(0, slash) : '';
}

function detailOf(error: unknown): string | null {
  const d = (error as { detail?: unknown } | undefined)?.detail;
  return typeof d === 'string' && d.trim() ? d : null;
}

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
        cost.tier === 'high' ? 'border-accent/60 text-accent' : 'border-line text-muted',
      ].join(' ')}
    >
      {cost.label}
      {perM != null ? <span className="ml-1 opacity-70">{`$${perM}/M`}</span> : null}
    </span>
  );
}

// One provider row: status, masked hint when connected, deep link, and the manager actions.
function ProviderRow({
  meta,
  status,
  canManage,
  busy,
  onConnect,
  onDisconnect,
  onRefresh,
}: {
  meta: ProviderMeta;
  status: ProviderStatus | null;
  canManage: boolean;
  busy: boolean;
  onConnect: (provider: string, apiKey: string) => Promise<boolean>;
  onDisconnect: (provider: string) => Promise<void>;
  onRefresh: (provider: string) => Promise<void>;
}) {
  const connected = status?.connected ?? false;
  const source = status?.source ?? null;
  const hint = status?.hint ?? null;

  const [open, setOpen] = useState(false);
  // The key lives in state only while a connect is in flight from this field. It is cleared on
  // success, on cancel, and whenever the field closes, and is never sent anywhere but the connect
  // call below.
  const [keyValue, setKeyValue] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [confirmOff, setConfirmOff] = useState(false);

  const closeField = useCallback(() => {
    setKeyValue('');
    setOpen(false);
  }, []);

  const submit = useCallback(async () => {
    const value = keyValue;
    if (!value.trim()) return;
    setConnecting(true);
    try {
      const ok = await onConnect(meta.slug, value);
      if (ok) {
        setKeyValue('');
        setOpen(false);
      }
    } finally {
      setConnecting(false);
    }
  }, [keyValue, meta.slug, onConnect]);

  return (
    <div className="border-b border-line/60 py-3 last:border-b-0">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex w-44 shrink-0 items-center gap-2">
          <StatusDot
            state={connected ? 'live' : 'pending'}
            label={connected ? `${meta.label} connected` : `${meta.label} not connected`}
          />
          <span className="text-sm font-semibold text-cream">{meta.label}</span>
        </div>
        <div className="flex-1 text-sm">
          {connecting ? (
            <span className="text-muted">connecting…</span>
          ) : connected ? (
            <span className="text-muted">
              connected
              {source === 'env' ? (
                <span className="ml-2 text-xs text-faint">via server .env</span>
              ) : hint ? (
                <span className="ml-2 font-mono text-xs text-cream">{hint}</span>
              ) : null}
            </span>
          ) : (
            <span className="text-faint">not connected</span>
          )}
        </div>
        {canManage ? (
          <div className="flex shrink-0 items-center gap-2">
            {connected && meta.hasModels && source === 'store' ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void onRefresh(meta.slug)}
                className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent disabled:opacity-60"
              >
                refresh models
              </button>
            ) : null}
            {connected && source === 'store' ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => setConfirmOff(true)}
                className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent disabled:opacity-60"
              >
                disconnect
              </button>
            ) : !connected ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => setOpen((v) => !v)}
                className="mono-label rounded-md border border-accent px-2 py-1 text-accent hover:bg-accent/10 disabled:opacity-60"
              >
                connect
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      {canManage && open && !connected ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-line bg-canvas/60 p-3">
          <input
            type="password"
            autoComplete="new-password"
            spellCheck={false}
            value={keyValue}
            onChange={(event) => setKeyValue(event.target.value)}
            placeholder={`${meta.label} API key`}
            aria-label={`${meta.label} API key`}
            className={`${INPUT} flex-1 font-mono`}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void submit();
            }}
          />
          <Button variant="primary" disabled={connecting || !keyValue.trim()} onClick={() => void submit()}>
            {connecting ? 'connecting' : 'connect'}
          </Button>
          <button
            type="button"
            onClick={closeField}
            className="mono-label rounded-md border border-line px-2 py-1 hover:text-cream"
          >
            cancel
          </button>
          {meta.keyUrl ? (
            <a
              href={meta.keyUrl}
              target="_blank"
              rel="noreferrer noopener"
              className="mono-label rounded-md border border-line px-2 py-1 text-muted hover:text-accent"
            >
              get a key ↗
            </a>
          ) : null}
        </div>
      ) : null}

      <ConfirmDialog
        open={confirmOff}
        title={`disconnect ${meta.label}`}
        body={`This removes the stored ${meta.label} key from the Brain. Models stay listed but cannot be used until you connect a key again. This never touches the server side .env.`}
        confirmLabel="Disconnect"
        busy={busy}
        onCancel={() => setConfirmOff(false)}
        onConfirm={() => {
          setConfirmOff(false);
          void onDisconnect(meta.slug);
        }}
      />
    </div>
  );
}

// The discovered models for one provider, each with an enable toggle. A model whose provider is
// not connected is shown disabled with a note, never as an error.
function ModelGroup({
  meta,
  connected,
  models,
  canManage,
  busy,
  onToggle,
}: {
  meta: ProviderMeta;
  connected: boolean;
  models: DiscoveredModel[];
  canManage: boolean;
  busy: boolean;
  onToggle: (model: DiscoveredModel, enabled: boolean) => Promise<void>;
}) {
  return (
    <div className="rounded-md border border-line bg-canvas/40 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold text-cream">{meta.label}</span>
        {!connected ? <span className="text-xs text-faint">not connected</span> : null}
      </div>
      {models.length === 0 ? (
        <p className="text-xs text-muted">
          {connected
            ? 'No models discovered yet. Use refresh models above.'
            : 'Connect this provider to discover its models.'}
        </p>
      ) : (
        <ul className="space-y-1">
          {models.map((model) => {
            const toggleDisabled = !canManage || busy || !connected;
            return (
              <li
                key={model.id}
                className="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 hover:bg-white/5"
              >
                <div className="min-w-0">
                  <div className="truncate font-mono text-xs text-cream">{model.model_id}</div>
                  {!connected ? (
                    <div className="text-xs text-faint">provider not connected</div>
                  ) : null}
                </div>
                <label className="flex shrink-0 items-center gap-2">
                  <span className="mono-label text-xs text-muted">
                    {model.enabled ? 'enabled' : 'disabled'}
                  </span>
                  <input
                    type="checkbox"
                    role="switch"
                    aria-label={`enable ${model.model_id}`}
                    checked={model.enabled}
                    disabled={toggleDisabled}
                    onChange={(event) => void onToggle(model, event.target.checked)}
                    className="h-4 w-4 accent-[color:var(--accent)] disabled:opacity-50"
                  />
                </label>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// A semantic key row. The remap control is a dropdown of enabled discovered models for the key's
// provider; when nothing is discovered yet it falls back to a read only display of the current
// models.yaml value, so the row is never empty on first load.
function KeyRow({
  entry,
  options,
  onRemap,
  busy,
}: {
  entry: ModelEntry;
  options: DiscoveredModel[];
  onRemap: (key: string, model: string) => Promise<void>;
  busy: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(entry.model);

  useEffect(() => {
    setValue(entry.model);
  }, [entry.model]);

  const hasOptions = options.length > 0;
  const currentInOptions = options.some((m) => m.model_id === entry.model);

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
        {editing && hasOptions ? (
          <select
            value={value}
            onChange={(event) => setValue(event.target.value)}
            aria-label={`model for ${entry.key}`}
            className={`${INPUT} w-full font-mono`}
          >
            {!currentInOptions ? (
              <option value={entry.model}>{`${entry.model} (current)`}</option>
            ) : null}
            {options.map((model) => (
              <option key={model.id} value={model.model_id}>
                {model.model_id}
              </option>
            ))}
          </select>
        ) : (
          <span className="font-mono text-sm text-muted">{entry.model}</span>
        )}
      </div>
      <CostBadge cost={entry.cost} />
      <div className="w-28 shrink-0 text-right">
        {editing && hasOptions ? (
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
              onClick={() => {
                setValue(entry.model);
                setEditing(false);
              }}
              className="mono-label rounded-md border border-line px-2 py-1 hover:text-cream"
            >
              cancel
            </button>
          </div>
        ) : hasOptions ? (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent"
          >
            remap
          </button>
        ) : (
          <span className="mono-label text-xs text-faint" title="connect the provider and refresh models to remap">
            no models yet
          </span>
        )}
      </div>
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
  const { me } = useAuth();
  const canManage = me?.role === 'owner' || me?.role === 'admin';

  const [config, setConfig] = useState<ModelsConfig | null>(null);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [models, setModels] = useState<DiscoveredModel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadProviders = useCallback(async () => {
    const [{ data: provData }, { data: modelData }] = await Promise.all([
      api.GET('/settings/providers'),
      api.GET('/settings/providers/models'),
    ]);
    setProviders((provData as ProviderStatus[]) ?? []);
    setModels((modelData as DiscoveredModel[]) ?? []);
  }, []);

  const loadConfig = useCallback(async () => {
    const { data, error: err } = await api.GET('/settings/models');
    if (err || !data) {
      setError('Could not load the model registry.');
      return;
    }
    setConfig(data as ModelsConfig);
  }, []);

  const load = useCallback(async () => {
    setError(null);
    await Promise.all([loadConfig(), loadProviders()]);
  }, [loadConfig, loadProviders]);

  useEffect(() => {
    void load();
  }, [load]);

  const statusBySlug = useMemo(() => {
    const map = new Map<string, ProviderStatus>();
    for (const status of providers) map.set(status.provider, status);
    return map;
  }, [providers]);

  const connectedSlugs = useMemo(() => {
    const set = new Set<string>();
    for (const status of providers) if (status.connected) set.add(status.provider);
    return set;
  }, [providers]);

  // Canonical providers first, then any extra provider the Brain reports that we do not list.
  const providerMetas = useMemo(() => {
    const metas = [...PROVIDERS];
    for (const status of providers) {
      if (!metas.some((m) => m.slug === status.provider)) metas.push(metaFor(status.provider));
    }
    return metas;
  }, [providers]);

  const enabledByProvider = useMemo(() => {
    const map = new Map<string, DiscoveredModel[]>();
    for (const model of models) {
      if (!model.enabled) continue;
      const list = map.get(model.provider) ?? [];
      list.push(model);
      map.set(model.provider, list);
    }
    return map;
  }, [models]);

  const connect = useCallback(
    async (provider: string, apiKey: string): Promise<boolean> => {
      setBusy(true);
      setError(null);
      try {
        // openapi-fetch leaves `error` undefined when a non-2xx body does not match the schema
        // (for example a bare 404). Gate on response.ok too so a failure is always surfaced and
        // never falls through to the success path.
        const { error: err, response } = await api.POST('/settings/providers/connect', {
          body: { provider, api_key: apiKey },
        });
        if (err || !response.ok) {
          setError(
            detailOf(err) ??
              `Could not connect ${provider} (HTTP ${response.status}). Check the key and try again.`,
          );
          return false;
        }
        await loadProviders();
        return true;
      } finally {
        setBusy(false);
      }
    },
    [loadProviders],
  );

  const disconnect = useCallback(
    async (provider: string) => {
      setBusy(true);
      setError(null);
      try {
        const { error: err, response } = await api.POST(
          '/settings/providers/{provider}/disconnect',
          { params: { path: { provider } } },
        );
        if (err || !response.ok) {
          setError(detailOf(err) ?? `Could not disconnect ${provider} (HTTP ${response.status}).`);
          return;
        }
        await loadProviders();
      } finally {
        setBusy(false);
      }
    },
    [loadProviders],
  );

  const refresh = useCallback(
    async (provider: string) => {
      setBusy(true);
      setError(null);
      try {
        const { error: err, response } = await api.POST(
          '/settings/providers/{provider}/refresh',
          { params: { path: { provider } } },
        );
        if (err || !response.ok) {
          setError(
            detailOf(err) ?? `Could not refresh models for ${provider} (HTTP ${response.status}).`,
          );
          return;
        }
        await loadProviders();
      } finally {
        setBusy(false);
      }
    },
    [loadProviders],
  );

  const toggleModel = useCallback(
    async (model: DiscoveredModel, enabled: boolean) => {
      setBusy(true);
      setError(null);
      try {
        const { error: err, response } = await api.PATCH(
          '/settings/providers/models/{model_id}',
          { params: { path: { model_id: model.id } }, body: { enabled } },
        );
        if (err || !response.ok) {
          // A 409 names the semantic keys still mapped to the model; surface it, never swallow it.
          setError(
            detailOf(err) ??
              `Could not ${enabled ? 'enable' : 'disable'} ${model.model_id} (HTTP ${response.status}).`,
          );
          return;
        }
        await loadProviders();
      } finally {
        setBusy(false);
      }
    },
    [loadProviders],
  );

  const remap = useCallback(
    async (key: string, model: string) => {
      setBusy(true);
      setError(null);
      try {
        const { error: err, response } = await api.PATCH('/settings/models/keys/{key}', {
          params: { path: { key } },
          body: { model },
        });
        if (err || !response.ok) {
          setError(
            detailOf(err) ??
              `Remap rejected (HTTP ${response.status}). Check the model id format (provider/model-id).`,
          );
          return;
        }
        await loadConfig();
      } finally {
        setBusy(false);
      }
    },
    [loadConfig],
  );

  if (!config) {
    return <p className="text-sm text-muted">{error ?? 'Loading the model registry…'}</p>;
  }

  return (
    <div className="space-y-8">
      <section>
        <MonoLabel tone="accent">API's</MonoLabel>
        <p className="mt-2 mb-3 max-w-prose text-sm text-muted">
          Connect a model provider once by handing it its API key. The key goes straight to the
          Brain and is never echoed back; only a masked last four hint is shown.
          {canManage ? null : ' Connecting and disconnecting is an owner or admin action.'}
        </p>
        <div className="rounded-glass border border-line bg-canvas/30 px-4">
          {providerMetas.map((meta) => (
            <ProviderRow
              key={meta.slug}
              meta={meta}
              status={statusBySlug.get(meta.slug) ?? null}
              canManage={canManage}
              busy={busy}
              onConnect={connect}
              onDisconnect={disconnect}
              onRefresh={refresh}
            />
          ))}
        </div>
      </section>

      <section>
        <MonoLabel tone="accent">discovered models</MonoLabel>
        <p className="mt-2 mb-3 max-w-prose text-sm text-muted">
          Models pulled live from each connected provider. Enable the ones you want available to
          the semantic keys. Disabling a model still mapped by a key is refused, and the message
          names the keys.
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          {providerMetas
            .filter((meta) => meta.hasModels)
            .map((meta) => (
              <ModelGroup
                key={meta.slug}
                meta={meta}
                connected={connectedSlugs.has(meta.slug)}
                models={models.filter((m) => m.provider === meta.slug)}
                canManage={canManage}
                busy={busy}
                onToggle={toggleModel}
              />
            ))}
        </div>
      </section>

      <section>
        <MonoLabel tone="accent">semantic keys</MonoLabel>
        <p className="mt-2 mb-3 max-w-prose text-sm text-muted">
          Business logic calls a key, never a model id. Remap a key to one of the enabled, discovered
          models for its provider and the router picks it up at once. The cost badge is a rough per
          million token hint.
        </p>
        <div className="rounded-glass border border-line bg-canvas/30 px-4">
          {config.keys.map((entry) => (
            <KeyRow
              key={entry.key}
              entry={entry}
              options={enabledByProvider.get(providerOf(entry.model)) ?? []}
              onRemap={remap}
              busy={busy}
            />
          ))}
        </div>
      </section>

      <section>
        <MonoLabel tone="accent">agents</MonoLabel>
        <p className="mt-2 mb-3 max-w-prose text-sm text-muted">
          Each agent runs through a semantic key, so a remap above changes the model an agent uses
          without any code change.
        </p>
        <AgentList agents={config.agents} />
      </section>

      {error ? <p className="text-sm text-danger">{error}</p> : null}
    </div>
  );
}
