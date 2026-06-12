import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../../app/client';
import { MonoLabel } from '../../../components/primitives';
import { Toggle } from './parts';

type KnowledgePolicy = Schemas['KnowledgePolicy'];

export function ApiConnectionsPanel() {
  const [policy, setPolicy] = useState<KnowledgePolicy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const { data, error: err } = await api.GET('/settings/knowledge-policy');
    if (err || !data) {
      setError('Could not load the policy.');
      return;
    }
    setError(null);
    setPolicy(data as KnowledgePolicy);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const patch = useCallback(async (changes: Partial<KnowledgePolicy>) => {
    setBusy(true);
    setError(null);
    try {
      const { data, error: err } = await api.PATCH('/settings/knowledge-policy', {
        body: changes,
      });
      if (err || !data) {
        setError('Could not save the policy.');
        return;
      }
      setPolicy(data as KnowledgePolicy);
    } finally {
      setBusy(false);
    }
  }, []);

  if (!policy) {
    return <p className="text-sm text-muted">{error ?? 'Loading the policy…'}</p>;
  }

  const minPct = Math.round(policy.memory_min_confidence * 100);

  return (
    <div className="space-y-8">
      <section>
        <MonoLabel tone="accent">ingestion</MonoLabel>
        <p className="mt-2 mb-2 max-w-prose text-sm text-muted">
          What the system may read in. Off by default; nothing is ingested until you allow it.
        </p>
        <div className="rounded-glass border border-line bg-canvas/30 px-4">
          <Toggle
            label="ChatGPT via API"
            hint="Allow the Brain to pull ChatGPT history through the OpenAI API."
            checked={policy.ingest_chatgpt_api}
            disabled={busy}
            onChange={(value) => void patch({ ingest_chatgpt_api: value })}
          />
          <Toggle
            label="Claude via API"
            hint="Allow the Brain to pull Claude history through the Anthropic API."
            checked={policy.ingest_claude_api}
            disabled={busy}
            onChange={(value) => void patch({ ingest_claude_api: value })}
          />
          <Toggle
            label="Connectors"
            hint="Allow installed connectors to feed items into the pipeline."
            checked={policy.ingest_connectors}
            disabled={busy}
            onChange={(value) => void patch({ ingest_connectors: value })}
          />
        </div>
      </section>

      <section>
        <MonoLabel tone="accent">long term memory</MonoLabel>
        <p className="mt-2 mb-2 max-w-prose text-sm text-muted">
          What is allowed into the Knowledge base. The human gate stays on by default: every
          candidate is reviewed in Dreaming before it becomes a memory.
        </p>
        <div className="rounded-glass border border-line bg-canvas/30 px-4">
          <Toggle
            label="Require explicit approval"
            hint="No candidate enters long term memory without an accept in the review queue."
            checked={policy.memory_require_approval}
            disabled={busy}
            onChange={(value) => void patch({ memory_require_approval: value })}
          />
          <Toggle
            label="Allow Dreaming memory"
            hint="Let the nightly Dreaming run propose memory candidates."
            checked={policy.memory_allow_dreaming}
            disabled={busy}
            onChange={(value) => void patch({ memory_allow_dreaming: value })}
          />
          <Toggle
            label="Allow connector memory"
            hint="Let connectors propose memory candidates."
            checked={policy.memory_allow_connectors}
            disabled={busy}
            onChange={(value) => void patch({ memory_allow_connectors: value })}
          />
          <div className="flex items-center justify-between gap-4 py-3">
            <div>
              <div className="text-sm text-cream">Minimum confidence</div>
              <div className="mt-0.5 text-xs text-muted">
                Candidates below this are not surfaced for review.
              </div>
            </div>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={policy.memory_min_confidence}
                disabled={busy}
                onChange={(event) =>
                  void patch({ memory_min_confidence: Number(event.target.value) })
                }
                className="w-40 accent-[color:var(--accent)]"
              />
              <span className="w-10 text-right font-mono text-xs text-muted">{minPct}%</span>
            </div>
          </div>
        </div>
      </section>

      {error ? <p className="text-sm text-accent">{error}</p> : null}
    </div>
  );
}
