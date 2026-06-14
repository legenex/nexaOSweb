import { useCallback, useEffect, useState } from 'react';

import { Button, GlassCard, MonoLabel, Pill } from '../../components/primitives';
import { loadFailures } from './runtimeCentral';
import type { FailureItem, Step } from './runtimeCentral';

function field(source: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return null;
}

function stringList(source: Record<string, unknown>, keys: string[]): string[] {
  for (const key of keys) {
    const value = source[key];
    if (Array.isArray(value)) return value.map((entry) => String(entry)).filter(Boolean);
  }
  return [];
}

// An advisory read on whether a resume could be safe, derived from the step's own risk tags.
// It is informational only: resume itself is a future capability with no retry control here.
function resumeSafe(step: Step): boolean {
  const payload = step.payload as Record<string, unknown>;
  const risk = payload.risk;
  if (!risk || typeof risk !== 'object') return false;
  const tags = risk as Record<string, unknown>;
  return (
    tags.reversible === true &&
    tags.local === true &&
    tags.destructive !== true &&
    tags.irreversible !== true
  );
}

function toolRef(step: Step): string | null {
  const call = step.tool_call as Record<string, unknown> | null;
  if (!call) return null;
  return field(call, ['name', 'command', 'tool']) ?? JSON.stringify(call);
}

function FailureCard({ item }: { item: FailureItem }) {
  const { step } = item;
  const failure = (step.failure ?? {}) as Record<string, unknown>;
  const errorRef = field(failure, ['error', 'message', 'detail']) ?? 'No error reference recorded.';
  const cause = field(failure, ['cause', 'likely_cause']);
  const suggestions = stringList(failure, ['suggestions', 'recovery', 'next_steps']);
  const tool = toolRef(step);
  const safe = resumeSafe(step);

  return (
    <GlassCard className="border-electric">
      <div className="mb-2 flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold text-cream">{step.title || step.kind}</h4>
        <Pill variant="grey">{step.status}</Pill>
      </div>

      <dl className="space-y-1 text-sm">
        <div>
          <span className="text-faint">attempted: </span>
          <span className="text-muted">{step.intent || 'Not recorded.'}</span>
        </div>
        <div>
          <span className="text-faint">error reference: </span>
          <span className="text-muted">{errorRef}</span>
        </div>
        {tool ? (
          <div>
            <span className="text-faint">tool or command: </span>
            <span className="text-muted">{tool}</span>
          </div>
        ) : null}
        <div>
          <span className="text-faint">likely cause: </span>
          <span className="text-muted">{cause ?? 'Not determined.'}</span>
          <span className="mono-meta text-faint"> (advisory)</span>
        </div>
        <div>
          <span className="text-faint">project: </span>
          <span className="text-muted">{item.projectName}</span>
          <span className="mono-meta text-faint"> · run #{item.runId} · step #{step.seq}</span>
        </div>
      </dl>

      {suggestions.length > 0 ? (
        <div className="mt-2">
          <MonoLabel tone="faint">recovery suggestions (advisory, model intent)</MonoLabel>
          <ul className="mt-1 list-disc pl-4 text-sm text-muted">
            {suggestions.map((suggestion, index) => (
              <li key={index}>{suggestion}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-3 flex items-center gap-2">
        <Pill variant={safe ? 'green' : 'grey'}>resume safe: {safe ? 'yes' : 'no'} (advisory)</Pill>
        {/* Resume is a future capability. No retry control is offered, because nothing here can
            safely retry a failed step yet. */}
        <Button variant="muted" disabled title="Resume is not available yet">
          Resume (future)
        </Button>
      </div>
    </GlassCard>
  );
}

export function FailureView() {
  const [items, setItems] = useState<FailureItem[] | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await loadFailures());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <MonoLabel tone="accent">failures</MonoLabel>
        {items ? <span className="mono-meta text-faint">{items.length}</span> : null}
      </div>

      {error ? (
        <p className="text-sm text-muted">The failure view is unavailable. Check the Brain connection.</p>
      ) : items === null ? (
        <p className="text-sm text-muted">Loading failures…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">No failed steps. Nothing needs attention here.</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {items.map((item) => (
            <FailureCard key={item.step.id} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}
