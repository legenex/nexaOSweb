import { useCallback, useEffect, useState } from 'react';

import { Button, GlassCard, MonoLabel, Pill } from '../../components/primitives';
import { loadApprovalQueue, resolveStep } from './runtimeCentral';
import type { ApprovalRequest, QueueItem } from './runtimeCentral';

function payloadString(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === 'string' && value.trim() ? value : null;
}

function risk(payload: Record<string, unknown>): Record<string, unknown> {
  const value = payload.risk;
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function whatCouldGoWrong(approval: ApprovalRequest): string {
  const payload = approval.payload as Record<string, unknown>;
  return (
    payloadString(payload, 'what_could_go_wrong') ??
    payloadString(payload, 'risk_note') ??
    (approval.materially_affects
      ? 'This decision materially affects the outcome.'
      : 'Low risk, no material effect recorded.')
  );
}

function undoNote(approval: ApprovalRequest): string {
  const payload = approval.payload as Record<string, unknown>;
  const explicit = payloadString(payload, 'undo_note') ?? payloadString(payload, 'undo');
  if (explicit) return explicit;
  return risk(payload).reversible === true ? 'Reversible.' : 'No undo recorded.';
}

function RiskBadge({ material }: { material: boolean }) {
  // Risk as colour plus icon, from brand classes only.
  return (
    <span className={material ? 'text-danger' : 'text-status-green'}>
      <span aria-hidden>{material ? '▲ ' : '● '}</span>
      <span className="mono-meta">{material ? 'high risk' : 'low risk'}</span>
    </span>
  );
}

function QueueCard({ item, busy, onResolve }: {
  item: QueueItem;
  busy: boolean;
  onResolve: (stepId: number, resolution: 'approved' | 'rejected') => void;
}) {
  const { approval } = item;
  const reason = approval.intent || payloadString(approval.payload as Record<string, unknown>, 'reason') || 'No reason recorded.';

  return (
    <GlassCard className="border-electric">
      <div className="mb-2 flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold text-cream">{approval.title || approval.kind}</h4>
        <RiskBadge material={approval.materially_affects} />
      </div>

      <dl className="space-y-1 text-sm">
        <div>
          <span className="text-faint">reason: </span>
          <span className="text-muted">{reason}</span>
        </div>
        <div>
          <span className="text-faint">what could go wrong: </span>
          <span className="text-muted">{whatCouldGoWrong(approval)}</span>
        </div>
        <div>
          <span className="text-faint">undo: </span>
          <span className="text-muted">{undoNote(approval)}</span>
        </div>
        <div>
          <span className="text-faint">project: </span>
          <span className="text-muted">{item.projectName}</span>
        </div>
      </dl>

      <div className="mt-3 flex items-center gap-2">
        <Pill variant={approval.recommended_default === 'proceed' ? 'green' : 'accent'}>
          default: {approval.recommended_default}
        </Pill>
        <span className="mono-meta text-faint">{approval.framing}</span>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          variant="primary"
          disabled={busy}
          onClick={() => onResolve(approval.id, 'approved')}
        >
          {busy ? 'working' : 'Approve'}
        </Button>
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => onResolve(approval.id, 'rejected')}
        >
          Reject
        </Button>
        {/* Modify is not a resolve_approval resolution; it is a disabled state, not a fake button. */}
        <Button variant="muted" disabled title="Modify is not supported yet">
          Modify
        </Button>
      </div>
    </GlassCard>
  );
}

export function ApprovalQueue() {
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await loadApprovalQueue());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const resolve = useCallback(
    async (stepId: number, resolution: 'approved' | 'rejected') => {
      setBusy(stepId);
      try {
        await resolveStep(stepId, resolution);
        await load();
      } finally {
        setBusy(null);
      }
    },
    [load],
  );

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <MonoLabel tone="accent">approval queue</MonoLabel>
        {items ? <span className="mono-meta text-faint">{items.length}</span> : null}
      </div>

      {error ? (
        <p className="text-sm text-muted">The approval queue is unavailable. Check the Brain connection.</p>
      ) : items === null ? (
        <p className="text-sm text-muted">Loading the queue…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">Nothing is waiting for approval.</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {items.map((item) => (
            <QueueCard
              key={item.approval.id}
              item={item}
              busy={busy === item.approval.id}
              onResolve={resolve}
            />
          ))}
        </div>
      )}
    </section>
  );
}
