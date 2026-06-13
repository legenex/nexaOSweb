import { useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { Button, GlassCard, Pill } from '../../components/primitives';

type Insight = Schemas['InsightRead'];

export type InsightActionKey = 'save' | 'task' | 'project' | 'dismiss';

const ACTIONS: { key: InsightActionKey; label: string }[] = [
  { key: 'save', label: 'Save to Knowledge' },
  { key: 'task', label: 'Turn into Task' },
  { key: 'project', label: 'Turn into Project' },
  { key: 'dismiss', label: 'Dismiss' },
];

// A resolved status reads as product green, an open one as brand accent.
const STATUS_TONE: Record<string, 'accent' | 'green' | 'grey'> = {
  active: 'accent',
  saved: 'green',
  tasked: 'green',
  project_created: 'green',
};

interface InsightCardProps {
  insight: Insight;
  onAct: (action: InsightActionKey, insight: Insight) => Promise<string>;
}

export function InsightCard({ insight, onAct }: InsightCardProps) {
  const [busy, setBusy] = useState<InsightActionKey | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const isOpen = insight.status === 'active';
  const confidence = Math.round((insight.confidence ?? 0) * 100);
  const refs = Array.isArray(insight.source_refs) ? insight.source_refs.length : 0;

  const run = async (key: InsightActionKey) => {
    setBusy(key);
    setNote(null);
    try {
      setNote(await onAct(key, insight));
    } catch (error) {
      setNote(error instanceof Error ? error.message : 'action failed');
    } finally {
      setBusy(null);
    }
  };

  return (
    <GlassCard className="border-electric">
      <div className="mb-2 flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold text-cream">{insight.title}</h4>
        <Pill variant={STATUS_TONE[insight.status] ?? 'grey'}>{insight.status}</Pill>
      </div>

      {insight.body ? <p className="text-sm text-muted">{insight.body}</p> : null}

      {/* Provenance: confidence, source, reasoning, and how many references back it. */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Pill variant="accent">{confidence}% confidence</Pill>
        <span className="mono-meta text-faint">source {insight.source}</span>
        {refs > 0 ? <span className="mono-meta text-faint">{refs} refs</span> : null}
        {insight.idea_kind ? <Pill variant="grey">{insight.idea_kind}</Pill> : null}
      </div>
      {insight.reasoning ? (
        <p className="mt-2 border-l border-line pl-3 text-xs text-muted">{insight.reasoning}</p>
      ) : null}

      {isOpen ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {ACTIONS.map((action) => (
            <Button
              key={action.key}
              variant={action.key === 'dismiss' ? 'muted' : 'outline'}
              disabled={busy !== null}
              onClick={() => void run(action.key)}
            >
              {busy === action.key ? 'working' : action.label}
            </Button>
          ))}
        </div>
      ) : null}

      {note ? <p className="mt-2 text-xs text-accent">{note}</p> : null}
    </GlassCard>
  );
}
