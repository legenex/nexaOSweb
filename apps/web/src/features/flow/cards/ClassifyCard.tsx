import { useState } from 'react';

import { Button, GlassCard, MonoLabel, Modal, Pill } from '../../../components/primitives';
import { useFlow } from '../FlowProvider';

// Shows the shape, confidence, and selected model with a one line why. The decision log
// modal shows the full record with no hidden chain of thought, plus an export action.
export function ClassifyCard() {
  const { selected } = useFlow();
  const [open, setOpen] = useState(false);
  const record = selected?.classification ?? null;

  function exportRecord() {
    if (!record) return;
    const blob = new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `classification-item-${record.item_id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  if (!record) {
    return (
      <GlassCard>
        <div className="mb-3 flex items-center justify-between">
          <MonoLabel tone="accent">classify verdict</MonoLabel>
        </div>
        <p className="text-sm text-muted">Awaiting classification.</p>
      </GlassCard>
    );
  }

  return (
    <GlassCard>
      <div className="mb-3 flex items-center justify-between">
        <MonoLabel tone="accent">classify verdict</MonoLabel>
        <MonoLabel tone="faint">model {record.recommended_model_key}</MonoLabel>
      </div>

      <div className="mb-3 flex items-center gap-2">
        <Pill variant="solid">{record.shape}</Pill>
        <MonoLabel tone="cream">conf {Math.round(record.confidence * 100)}%</MonoLabel>
      </div>

      <p className="mb-3 line-clamp-3 text-sm text-muted">{record.reasoning_summary}</p>

      <Button variant="outline" onClick={() => setOpen(true)}>
        Decision log
      </Button>

      <Modal open={open} title="decision log" onClose={() => setOpen(false)}>
        <dl className="space-y-3 text-sm">
          <Row label="shape" value={record.shape} />
          <Row label="confidence" value={`${Math.round(record.confidence * 100)}%`} />
          <Row label="recommended route" value={record.recommended_route} />
          <Row label="model key" value={record.recommended_model_key} />
          <Row label="resolved model" value={record.resolved_model_id} />
          <Row label="rationale" value={record.model_rationale} />
          <Row label="reasoning summary" value={record.reasoning_summary} />
          {record.tags.length ? (
            <div className="flex flex-wrap gap-1.5">
              {record.tags.map((tag) => (
                <Pill key={String(tag)} variant="grey">
                  {String(tag)}
                </Pill>
              ))}
            </div>
          ) : null}
        </dl>
        <div className="mt-4">
          <Button variant="muted" onClick={exportRecord}>
            Export to file
          </Button>
        </div>
      </Modal>
    </GlassCard>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <MonoLabel tone="faint">{label}</MonoLabel>
      <dd className="mt-0.5 text-cream">{value}</dd>
    </div>
  );
}
