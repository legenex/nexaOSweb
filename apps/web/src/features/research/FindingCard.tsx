import { useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { Button, GlassCard, MonoLabel, Pill } from '../../components/primitives';

type ResearchFinding = Schemas['ResearchFindingRead'];

export type FindingActionKey = 'add' | 'brief' | 'task' | 'builder' | 'knowledge';

// The five finding level actions. Add to Project and Update Project Brief write into the
// attached build project, so they need an attachment first.
const ACTIONS: { key: FindingActionKey; label: string; needsAttach: boolean }[] = [
  { key: 'add', label: 'Add to Project', needsAttach: true },
  { key: 'brief', label: 'Update Project Brief', needsAttach: true },
  { key: 'task', label: 'Create Task', needsAttach: false },
  { key: 'builder', label: 'Send to Project Builder', needsAttach: false },
  { key: 'knowledge', label: 'Save to Knowledge', needsAttach: false },
];

interface FindingCardProps {
  finding: ResearchFinding;
  isAttached: boolean;
  onAct: (action: FindingActionKey, finding: ResearchFinding) => Promise<string>;
}

export function FindingCard({ finding, isAttached, onAct }: FindingCardProps) {
  const [busy, setBusy] = useState<FindingActionKey | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const run = async (key: FindingActionKey) => {
    setBusy(key);
    setNote(null);
    try {
      setNote(await onAct(key, finding));
    } catch (error) {
      setNote(error instanceof Error ? error.message : 'action failed');
    } finally {
      setBusy(null);
    }
  };

  return (
    <GlassCard className="border-electric">
      <div className="mb-2 flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold text-cream">{finding.title}</h4>
        <Pill variant={finding.status === 'new' ? 'accent' : 'green'}>{finding.status}</Pill>
      </div>
      {finding.detail ? <p className="text-sm text-muted">{finding.detail}</p> : null}
      {finding.url ? (
        <a
          href={finding.url}
          target="_blank"
          rel="noreferrer"
          className="mono-meta mt-1 block truncate text-accent hover:underline"
        >
          {finding.url}
        </a>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        {ACTIONS.map((action) => {
          const disabled = busy !== null || (action.needsAttach && !isAttached);
          return (
            <Button
              key={action.key}
              variant="muted"
              disabled={disabled}
              onClick={() => void run(action.key)}
            >
              {busy === action.key ? 'working' : action.label}
            </Button>
          );
        })}
      </div>

      {!isAttached ? (
        <MonoLabel tone="faint" className="mt-2 block">
          attach a project to enable project actions
        </MonoLabel>
      ) : null}
      {note ? <p className="mt-2 text-xs text-accent">{note}</p> : null}
    </GlassCard>
  );
}
