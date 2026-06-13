import { useState } from 'react';

import { Button, MonoLabel, Pill } from '../../../components/primitives';
import { applyEdit, proposeEdit, rollbackEdit } from './api';
import type { EditorProposal } from './api';
import { ConfirmDialog } from './ConfirmDialog';

type EntryStatus = 'proposed' | 'applying' | 'applied' | 'rolling' | 'rolled_back';

interface ProposalEntry {
  id: number;
  instruction: string;
  proposal: EditorProposal;
  status: EntryStatus;
  buildLogId: number | null;
  error: string | null;
}

// The AI Editor. A chat to request a change: the gated propose endpoint returns a diff
// summary, the user must Approve to apply (which writes a build log entry), and an applied
// change can be rolled back behind a second confirmation. Apply and rollback never run
// without an explicit, deliberate action.
export function AiEditorTab({ projectId, onChange }: { projectId: number; onChange?: () => void }) {
  const [filePath, setFilePath] = useState('project_plan.md');
  const [instruction, setInstruction] = useState('');
  const [entries, setEntries] = useState<ProposalEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmFor, setConfirmFor] = useState<number | null>(null);

  const update = (id: number, patch: Partial<ProposalEntry>) =>
    setEntries((prev) => prev.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry)));

  const send = async () => {
    const file = filePath.trim();
    const text = instruction.trim();
    if (!file || !text) {
      setError('Name a file and describe the change.');
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const proposal = await proposeEdit(projectId, file, text);
      setEntries((prev) => [
        ...prev,
        {
          id: proposal.proposal_id,
          instruction: text,
          proposal,
          status: 'proposed',
          buildLogId: null,
          error: null,
        },
      ]);
      setInstruction('');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const approve = async (entry: ProposalEntry) => {
    update(entry.id, { status: 'applying', error: null });
    try {
      const result = await applyEdit(projectId, entry.proposal.proposal_id);
      update(entry.id, { status: 'applied', buildLogId: result.build_log_id });
      onChange?.();
    } catch (err) {
      update(entry.id, { status: 'proposed', error: (err as Error).message });
    }
  };

  const doRollback = async (entry: ProposalEntry) => {
    if (entry.buildLogId === null) return;
    update(entry.id, { status: 'rolling', error: null });
    try {
      await rollbackEdit(projectId, entry.buildLogId);
      update(entry.id, { status: 'rolled_back' });
      onChange?.();
    } catch (err) {
      update(entry.id, { status: 'applied', error: (err as Error).message });
    } finally {
      setConfirmFor(null);
    }
  };

  const confirmEntry = entries.find((entry) => entry.id === confirmFor) ?? null;

  return (
    <div className="space-y-4">
      <div className="rounded-glass border border-line bg-surface/60 p-4">
        <MonoLabel tone="accent" className="mb-3 block">
          request a change
        </MonoLabel>
        <label className="mb-2 block">
          <MonoLabel tone="faint" className="mb-1 block">
            file path
          </MonoLabel>
          <input
            value={filePath}
            onChange={(event) => setFilePath(event.target.value)}
            placeholder="project_plan.md"
            className="w-full rounded-lg border border-line bg-black/30 px-3 py-2 font-mono text-xs text-cream outline-none focus:border-accent"
          />
        </label>
        <label className="block">
          <MonoLabel tone="faint" className="mb-1 block">
            instruction
          </MonoLabel>
          <textarea
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            rows={3}
            placeholder="Describe the change you want the editor to make."
            className="w-full rounded-lg border border-line bg-black/30 px-3 py-2 text-sm text-cream outline-none focus:border-accent"
          />
        </label>
        {error ? <p className="mt-2 text-xs text-danger">{error}</p> : null}
        <div className="mt-3">
          <Button variant="primary" onClick={() => void send()} disabled={busy}>
            {busy ? 'Proposing' : 'Propose change'}
          </Button>
        </div>
      </div>

      {entries.length === 0 ? (
        <p className="text-sm text-muted">
          Proposed changes appear here as a diff summary. Nothing is written until you Approve.
        </p>
      ) : (
        <ol className="space-y-4">
          {entries.map((entry) => (
            <li key={entry.id} className="rounded-glass border border-line bg-surface/60 p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <MonoLabel tone="faint">{entry.proposal.file_path}</MonoLabel>
                <Pill
                  variant={
                    entry.status === 'applied'
                      ? 'green'
                      : entry.status === 'rolled_back'
                        ? 'grey'
                        : 'accent'
                  }
                >
                  {entry.status.replace('_', ' ')}
                </Pill>
              </div>
              <p className="mb-2 text-sm text-cream">
                <span className="text-muted">you: </span>
                {entry.instruction}
              </p>
              <p className="mb-1 text-sm text-cream">{entry.proposal.summary}</p>
              <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line bg-black/30 p-2 font-mono text-[0.7rem] text-muted">
                {entry.proposal.diff_summary}
              </pre>
              {entry.error ? <p className="mt-2 text-xs text-danger">{entry.error}</p> : null}

              <div className="mt-3 flex flex-wrap gap-2">
                {entry.status === 'proposed' || entry.status === 'applying' ? (
                  <Button
                    variant="primary"
                    onClick={() => void approve(entry)}
                    disabled={entry.status === 'applying'}
                  >
                    {entry.status === 'applying' ? 'Applying' : 'Approve and apply'}
                  </Button>
                ) : null}
                {entry.status === 'applied' || entry.status === 'rolling' ? (
                  <Button
                    variant="outline"
                    onClick={() => setConfirmFor(entry.id)}
                    disabled={entry.status === 'rolling'}
                  >
                    {entry.status === 'rolling' ? 'Rolling back' : 'Roll back'}
                  </Button>
                ) : null}
                {entry.status === 'applied' && entry.buildLogId !== null ? (
                  <MonoLabel tone="faint">build log #{entry.buildLogId}</MonoLabel>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      )}

      <ConfirmDialog
        open={confirmFor !== null}
        title="roll back change"
        body="This overwrites the file on disk with its previous content and records a rollback in the build log. This cannot be undone from here."
        confirmLabel="Roll back"
        busy={confirmEntry?.status === 'rolling'}
        onConfirm={() => confirmEntry && void doRollback(confirmEntry)}
        onCancel={() => setConfirmFor(null)}
      />
    </div>
  );
}
