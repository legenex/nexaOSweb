import { useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { GlassCard, Pill } from '../../components/primitives';
import { OverflowMenu } from '../../components/OverflowMenu';
import type { OverflowItem } from '../../components/OverflowMenu';

type Insight = Schemas['InsightRead'];

export type InsightActionKey = 'save' | 'task' | 'project' | 'dismiss';

// The per-insight overflow menu, in display order. Each maps to an existing endpoint through
// onAct. Dismiss is last and marked danger, matching the kebab convention for the action that
// removes the card from the queue.
const MENU: { key: InsightActionKey; label: string; danger?: boolean }[] = [
  { key: 'save', label: 'Save to Knowledge' },
  { key: 'task', label: 'Create task' },
  { key: 'dismiss', label: 'Dismiss', danger: true },
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

  // Actions exist only while the insight is still open and no action is in flight. An empty
  // list leaves the menu visibly disabled rather than offering moves that cannot apply.
  const items: OverflowItem[] =
    isOpen && busy === null
      ? MENU.map((action) => ({
          label: action.label,
          danger: action.danger,
          onClick: () => void run(action.key),
        }))
      : [];

  const menuLabel = isOpen
    ? busy
      ? 'Working'
      : `Actions for ${insight.title}`
    : `No actions, this insight is ${insight.status}`;

  return (
    <GlassCard className="border-electric">
      <div className="mb-2 flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold text-cream">{insight.title}</h4>
        <div className="flex shrink-0 items-center gap-2">
          <Pill variant={STATUS_TONE[insight.status] ?? 'grey'}>{insight.status}</Pill>
          <OverflowMenu label={menuLabel} items={items} disabled={!isOpen || busy !== null} />
        </div>
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

      {busy ? <p className="mt-3 text-xs text-muted">working…</p> : null}
      {note ? <p className="mt-2 text-xs text-accent">{note}</p> : null}
    </GlassCard>
  );
}
