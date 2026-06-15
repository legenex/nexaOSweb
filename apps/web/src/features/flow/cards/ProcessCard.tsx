import { useState } from 'react';

import { Button, GlassCard, MonoLabel } from '../../../components/primitives';
import { Modal } from '../../../components/primitives';
import { useFlow } from '../FlowProvider';
import { renderMarkdown } from '../markdown';

// Shows the project folder and build destination, with an Open plan modal that renders the
// markdown. If the project has not been processed yet, offers to run Process.
export function ProcessCard() {
  const { selected, process, getPlan, downloadArchive } = useFlow();
  const [open, setOpen] = useState(false);
  const [plan, setPlan] = useState('');
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isProject = selected?.route === 'project';
  const planReady = Boolean(selected?.plan_available);

  async function runProcess() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await process(selected.id);
    } catch {
      setError('Process failed. Check the Brain connection.');
    } finally {
      setBusy(false);
    }
  }

  async function openPlan() {
    if (!selected) return;
    setPlan(await getPlan(selected.id));
    setOpen(true);
  }

  async function download() {
    if (!selected) return;
    setDownloading(true);
    setError(null);
    try {
      await downloadArchive(selected.id);
    } catch {
      setError('Download failed. Run Process first, then try again.');
    } finally {
      setDownloading(false);
    }
  }

  if (!isProject) {
    return (
      <GlassCard>
        <MonoLabel tone="accent">project plan</MonoLabel>
        <p className="mt-2 text-sm text-muted">Process applies to project shaped items.</p>
      </GlassCard>
    );
  }

  return (
    <GlassCard active={planReady}>
      <div className="mb-3 flex items-center justify-between">
        <MonoLabel tone="accent">project plan</MonoLabel>
        {selected?.build_destination ? (
          <MonoLabel tone="faint">build</MonoLabel>
        ) : null}
      </div>

      <div className="mb-3 rounded-lg border border-line bg-canvas/60 p-2 font-mono text-xs text-muted">
        project_plan.md {planReady ? '' : '[not built]'}
      </div>

      {selected?.build_destination ? (
        <p className="mb-3 text-sm">
          <span className="text-muted">destination </span>
          <span className="text-accent">{selected.build_destination}</span>
        </p>
      ) : null}

      {error ? <p className="mb-2 text-xs text-danger">{error}</p> : null}

      <div className="flex flex-wrap gap-2">
        {planReady ? (
          <>
            <Button variant="outline" onClick={() => void openPlan()}>
              Open project_plan.md
            </Button>
            <Button variant="outline" onClick={() => void download()} disabled={downloading}>
              {downloading ? 'Preparing' : 'Download folder (.zip)'}
            </Button>
          </>
        ) : (
          <Button variant="primary" onClick={() => void runProcess()} disabled={busy}>
            {busy ? 'Processing' : 'Run process'}
          </Button>
        )}
      </div>

      <Modal open={open} title="project_plan.md" onClose={() => setOpen(false)}>
        {renderMarkdown(plan)}
      </Modal>
    </GlassCard>
  );
}
