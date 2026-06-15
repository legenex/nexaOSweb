import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { GlassCard, MonoLabel, Pill, StatusDot } from '../../components/primitives';
import type { DotState } from '../../components/primitives';

type ProviderStatus = Schemas['ProviderStatus'];
type ModelsConfig = Schemas['ModelsConfig'];
type ModelUsage = Schemas['ModelUsage'];

// Friendly names for the model providers. The slug stays the source of truth on the wire; this
// is presentation only, so anthropic reads as Claude and xai reads as Grok.
const PROVIDER_LABEL: Record<string, string> = {
  anthropic: 'Claude',
  openai: 'OpenAI',
  gemini: 'Gemini',
  xai: 'Grok',
  grok: 'Grok',
  mistral: 'Mistral',
  cohere: 'Cohere',
  groq: 'Groq',
};

function providerLabel(slug: string): string {
  return PROVIDER_LABEL[slug] ?? slug.charAt(0).toUpperCase() + slug.slice(1);
}

function providerState(status: string): DotState {
  if (status === 'connected') return 'live';
  if (status === 'error' || status === 'failed') return 'error';
  return 'pending';
}

// Strip the provider prefix so a long id like anthropic/claude-opus-4-8 reads as the model name.
function shortModel(model: string | null | undefined): string {
  if (!model) return 'unmapped';
  const slash = model.indexOf('/');
  return slash === -1 ? model : model.slice(slash + 1);
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <MonoLabel tone="accent">{title}</MonoLabel>
      <div className="mt-2 space-y-1.5">{children}</div>
    </div>
  );
}

// The AI systems rail. What is wired into the brain right now: which model providers hold a live
// key (the AI connections), the agents and the model each one runs through, and how often each
// semantic key has fired. All reads only, no secret ever crosses the wire.
export function AISystems({ usage = [] }: { usage?: ModelUsage[] }) {
  const [providers, setProviders] = useState<ProviderStatus[] | null>(null);
  const [config, setConfig] = useState<ModelsConfig | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    void (async () => {
      const [prov, models] = await Promise.all([
        api.GET('/settings/providers'),
        api.GET('/settings/models'),
      ]);
      if (!active) return;
      if (prov.error || models.error) {
        setError(true);
        return;
      }
      setProviders((prov.data as ProviderStatus[]) ?? []);
      setConfig((models.data as ModelsConfig) ?? null);
    })();
    return () => {
      active = false;
    };
  }, []);

  return (
    <GlassCard className="border-electric">
      <div className="mb-3 flex items-center justify-between">
        <MonoLabel tone="accent">ai systems</MonoLabel>
        <span className="mono-meta text-faint">connections · agents</span>
      </div>

      {error ? (
        <p className="text-sm text-muted">AI systems are unavailable. Check the Brain connection.</p>
      ) : !providers || !config ? (
        <p className="text-sm text-muted">Reading the model stack…</p>
      ) : (
        <div className="space-y-5">
          <Section title="ai connections">
            {providers.length === 0 ? (
              <p className="text-sm text-muted">No providers known.</p>
            ) : (
              providers.map((provider) => (
                <div key={provider.provider} className="flex items-center gap-2">
                  <StatusDot state={providerState(provider.status)} />
                  <span className="text-sm text-cream">{providerLabel(provider.provider)}</span>
                  {provider.connected ? (
                    <Pill variant="green" className="ml-1">
                      {provider.source === 'env' ? 'env key' : 'active'}
                    </Pill>
                  ) : (
                    <Pill variant="grey" className="ml-1">
                      not connected
                    </Pill>
                  )}
                  {provider.hint ? (
                    <span className="mono-meta ml-auto text-faint">{provider.hint}</span>
                  ) : null}
                </div>
              ))
            )}
          </Section>

          <Section title="agents">
            {config.agents.length === 0 ? (
              <p className="text-sm text-muted">No agents configured.</p>
            ) : (
              config.agents.map((agent) => (
                <div key={agent.id} className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm text-cream" title={agent.description}>
                    {agent.label}
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    <Pill variant="grey">{agent.model_key}</Pill>
                    <span className="mono-meta text-faint">
                      {shortModel(agent.resolved_model)}
                    </span>
                  </span>
                </div>
              ))
            )}
          </Section>

          {usage.length > 0 ? (
            <Section title="model usage">
              {usage.map((row) => (
                <div key={row.model_key} className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs text-cream">{row.model_key}</span>
                  <span className="mono-meta text-faint">{row.count}</span>
                </div>
              ))}
            </Section>
          ) : null}
        </div>
      )}
    </GlassCard>
  );
}
