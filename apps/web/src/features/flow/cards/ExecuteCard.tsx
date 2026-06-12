import { useState } from 'react';

import { Button, GlassCard, MonoLabel, StatusDot } from '../../../components/primitives';
import { useNavigation } from '../../../app/navigation';
import { useFlow } from '../FlowProvider';

const WORKERS = ['planner', 'developer', 'reviewer', 'qa'];

// Promotes an approved project to the builder and shows a worker list that lights up, then a
// deep link into the Projects tab where the build, build review gate, and live stages run.
export function ExecuteCard() {
  const { selected, promote } = useFlow();
  const navigate = useNavigation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!selected || selected.route !== 'project' || !selected.project_id) {
    return (
      <GlassCard>
        <MonoLabel tone="accent">execute</MonoLabel>
        <p className="mt-2 text-sm text-muted">Execute applies to project shaped items.</p>
      </GlassCard>
    );
  }

  const promoted = selected.project_stage === 'build';
  const approved = selected.gate_state === 'approved';

  async function onPromote() {
    setBusy(true);
    setError(null);
    try {
      await promote(selected!.id);
    } catch {
      setError('Promote failed. The project must be approved first.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <GlassCard active={promoted}>
      <div className="mb-3 flex items-center justify-between">
        <MonoLabel tone="accent">execute</MonoLabel>
        {promoted ? <MonoLabel tone="faint">handed off</MonoLabel> : null}
      </div>

      <div className="mb-3 rounded-lg border border-line bg-canvas/60 p-2 font-mono text-xs text-muted">
        /promote project
      </div>

      <ul className="mb-3 space-y-1.5">
        {WORKERS.map((worker) => (
          <li key={worker} className="flex items-center gap-2">
            <StatusDot state={promoted ? 'live' : 'pending'} />
            <span className={promoted ? 'text-sm text-cream' : 'text-sm text-muted'}>{worker}</span>
          </li>
        ))}
      </ul>

      {error ? <p className="mb-2 text-xs text-danger">{error}</p> : null}

      {promoted ? (
        <Button variant="outline" onClick={() => navigate('projects')}>
          Open in Projects
        </Button>
      ) : (
        <Button variant="primary" onClick={() => void onPromote()} disabled={busy || !approved}>
          {busy ? 'Promoting' : 'Promote to builder'}
        </Button>
      )}
    </GlassCard>
  );
}
