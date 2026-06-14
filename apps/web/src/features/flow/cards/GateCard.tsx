import { useState } from 'react';

import { Button, GlassCard, MonoLabel, Modal, Pill } from '../../../components/primitives';
import { useFlow } from '../FlowProvider';
import { renderMarkdown } from '../markdown';
import { ReadinessPanel, type ReadinessSnapshot } from './ReadinessPanel';

// Reuses the project gate. Approve as live, Send back to Clarify, or Archive. Surfaces the
// build destination and selected integrations, with links to the plan and preview.
export function GateCard() {
  const { selected, approve, reject, getPlan, getPreview } = useFlow();
  const [busy, setBusy] = useState<string | null>(null);
  const [planOpen, setPlanOpen] = useState(false);
  const [plan, setPlan] = useState('');
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<ReadinessSnapshot>({
    assessed: false,
    satisfied: false,
    blocking: [],
  });

  if (!selected || selected.route !== 'project' || !selected.project_id) {
    return (
      <GlassCard>
        <MonoLabel tone="accent">gate</MonoLabel>
        <p className="mt-2 text-sm text-muted">The gate applies to project shaped items.</p>
      </GlassCard>
    );
  }

  const projectId = selected.project_id;
  const gate = selected.gate_state;

  async function run(action: 'approve' | 'sendback' | 'archive') {
    setBusy(action);
    setError(null);
    try {
      if (action === 'approve') await approve(projectId);
      else if (action === 'sendback') await reject(projectId, 'needs changes');
      else await reject(projectId, 'archived');
    } catch {
      setError('Gate action failed.');
    } finally {
      setBusy(null);
    }
  }

  async function openPlan() {
    setPlan(await getPlan(selected!.id));
    setPlanOpen(true);
  }

  return (
    <GlassCard active={gate === 'approved'}>
      <div className="mb-3 flex items-center justify-between">
        <MonoLabel tone="accent">human gate</MonoLabel>
        <Pill variant={gate === 'approved' ? 'green' : gate === 'rejected' ? 'grey' : 'accent'}>
          {gate}
        </Pill>
      </div>

      <div className="mb-3 space-y-1 text-sm">
        <p>
          <span className="text-muted">build </span>
          <span className="text-accent">{selected.build_destination ?? 'not set'}</span>
        </p>
        <div className="flex flex-wrap gap-1.5">
          {(selected.selected_integrations ?? []).map((value) => (
            <Pill key={String(value)} variant="green">
              {String(value)}
            </Pill>
          ))}
        </div>
      </div>

      {error ? <p className="mb-2 text-xs text-danger">{error}</p> : null}

      <div className="mb-3 flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => void openPlan()}>
          Open plan
        </Button>
        {selected.preview_available ? (
          <Button variant="outline" onClick={() => void getPreview(selected.id).then(setPreview)}>
            Open preview
          </Button>
        ) : null}
      </div>

      <div className="mb-4">
        <ReadinessPanel itemId={selected.id} onChange={setReadiness} />
      </div>

      {!readiness.satisfied ? (
        <p className="mb-2 text-xs text-muted">
          {readiness.assessed
            ? `Approve is held until readiness is satisfied. Blocking: ${readiness.blocking.join(', ')}`
            : 'Run the readiness check before approving the build.'}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button
          variant="primary"
          onClick={() => void run('approve')}
          disabled={busy !== null || !readiness.satisfied}
          title={readiness.satisfied ? undefined : 'Resolve the blocking readiness items first'}
        >
          {busy === 'approve' ? 'Approving' : 'Approve as live'}
        </Button>
        <Button variant="muted" onClick={() => void run('sendback')} disabled={busy !== null}>
          Send back
        </Button>
        <Button variant="muted" onClick={() => void run('archive')} disabled={busy !== null}>
          Archive
        </Button>
      </div>

      <Modal open={planOpen} title="project_plan.md" onClose={() => setPlanOpen(false)}>
        {renderMarkdown(plan)}
      </Modal>
      <Modal open={preview !== null} title="project_preview.html" onClose={() => setPreview(null)}>
        <iframe
          title="project preview"
          srcDoc={preview ?? ''}
          className="h-[420px] w-full rounded-lg border border-line bg-white"
        />
      </Modal>
    </GlassCard>
  );
}
