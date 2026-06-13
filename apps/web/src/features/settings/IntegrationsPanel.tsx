import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { Button, MonoLabel, Pill, StatusDot } from '../../components/primitives';

type Integration = Schemas['IntegrationRead'];

interface Provider {
  id: string;
  label: string;
}

// Connectable providers grouped by purpose. The id is the canonical lowercase provider key
// the connect endpoint stores.
const GROUPS: Array<{ group: string; providers: Provider[] }> = [
  {
    group: 'Communication',
    providers: [
      { id: 'gmail', label: 'Gmail' },
      { id: 'slack', label: 'Slack' },
      { id: 'telegram', label: 'Telegram' },
    ],
  },
  {
    group: 'Files',
    providers: [
      { id: 'google_drive', label: 'Google Drive' },
      { id: 'dropbox', label: 'Dropbox' },
    ],
  },
  {
    group: 'Development',
    providers: [
      { id: 'github', label: 'GitHub' },
      { id: 'gitlab', label: 'GitLab' },
    ],
  },
  {
    group: 'Data',
    providers: [
      { id: 'airtable', label: 'Airtable' },
      { id: 'google_sheets', label: 'Google Sheets' },
    ],
  },
  {
    group: 'AI providers',
    providers: [
      { id: 'anthropic', label: 'Anthropic' },
      { id: 'openai', label: 'OpenAI' },
      { id: 'gemini', label: 'Google Gemini' },
    ],
  },
];

// These need a separate Brain addition (store credentials and review APIs), so they are shown
// disabled as coming soon and are not wired.
const COMING_SOON = ['Apple App Store Connect', 'Google Play Console'];

export function IntegrationsPanel() {
  const [rows, setRows] = useState<Integration[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    const { data } = await api.GET('/integrations');
    setRows((data as Integration[]) ?? []);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const connected = (providerId: string) =>
    rows?.find((r) => r.provider === providerId && r.status === 'connected') ?? null;

  const connect = async (providerId: string) => {
    setBusy(providerId);
    await api.POST('/integrations/connect', { body: { provider: providerId } });
    await load();
    setBusy(null);
  };

  const disconnect = async (id: number, providerId: string) => {
    setBusy(providerId);
    await api.POST('/integrations/{integration_id}/disconnect', {
      params: { path: { integration_id: id } },
    });
    await load();
    setBusy(null);
  };

  if (!rows) return <MonoLabel tone="faint">loading integrations</MonoLabel>;

  return (
    <div className="max-w-2xl space-y-6">
      {GROUPS.map(({ group, providers }) => (
        <section key={group}>
          <MonoLabel tone="accent" className="mb-2 block">
            {group}
          </MonoLabel>
          <ul className="divide-y divide-line/60 rounded-glass border border-line bg-surface/40">
            {providers.map((provider) => {
              const row = connected(provider.id);
              const isConnected = row !== null;
              return (
                <li key={provider.id} className="flex items-center gap-3 px-4 py-3">
                  <StatusDot state={isConnected ? 'live' : 'pending'} label={provider.label} />
                  <span className="flex-1 text-sm text-cream">{provider.label}</span>
                  {isConnected ? (
                    <button
                      type="button"
                      onClick={() => void disconnect(row.id, provider.id)}
                      disabled={busy === provider.id}
                      className="mono-label rounded-md border border-line px-3 py-1 text-muted hover:border-danger hover:text-danger disabled:opacity-50"
                    >
                      disconnect
                    </button>
                  ) : (
                    <Button
                      variant="outline"
                      onClick={() => void connect(provider.id)}
                      disabled={busy === provider.id}
                    >
                      {busy === provider.id ? 'Connecting' : 'Connect'}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      <section>
        <MonoLabel tone="accent" className="mb-2 block">
          App stores
        </MonoLabel>
        <ul className="divide-y divide-line/60 rounded-glass border border-line bg-surface/40">
          {COMING_SOON.map((label) => (
            <li key={label} className="flex items-center gap-3 px-4 py-3 opacity-60">
              <StatusDot state="pending" label={label} />
              <span className="flex-1 text-sm text-cream">{label}</span>
              <Pill variant="grey">coming soon</Pill>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
