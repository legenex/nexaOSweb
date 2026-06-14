import { useCallback, useEffect, useState } from 'react';

import { OverflowMenu } from '../../../components/OverflowMenu';
import { Button, MonoLabel, Pill, StatusDot } from '../../../components/primitives';
import type { DotState } from '../../../components/primitives';
import { useNavigation } from '../../../app/navigation';
import { ConfirmDialog } from '../../projects/workspace/ConfirmDialog';
import {
  fetchReadiness,
  provideCredential,
  runReadiness,
  type ReadinessAssessment,
  type ReadinessItem,
} from '../readiness';

// The five classes, in the order the gate bands them. A class with no item is not rendered.
const CATEGORIES: { key: string; label: string }[] = [
  { key: 'integrations', label: 'Integrations' },
  { key: 'credentials', label: 'Credentials' },
  { key: 'decisions', label: 'Decisions' },
  { key: 'data_sources', label: 'Data sources' },
  { key: 'unknowns', label: 'Unknowns' },
];

function dotState(item: ReadinessItem): DotState {
  if (item.satisfied) return 'done';
  if (item.resolution === 'needs_credential') return 'warn';
  if (item.resolution === 'needs_user') return 'gate';
  return 'pending'; // unknown, non blocking
}

function stateLabel(item: ReadinessItem): string {
  if (item.satisfied) return item.source ? `answered by ${item.source}` : 'resolved';
  if (item.resolution === 'needs_credential') return 'needs a credential';
  if (item.resolution === 'needs_user') return 'needs your answer';
  if (item.resolution === 'unknown') return 'unknown, not blocking';
  return item.resolution ?? 'pending';
}

export interface ReadinessSnapshot {
  assessed: boolean;
  satisfied: boolean;
  blocking: string[];
}

type View =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'unassessed' }
  | { kind: 'assessed'; assessment: ReadinessAssessment };

// The build readiness panel for the Human Gate. Shows the assessment grouped by class, links
// blocking items into the approval queue, provides credentials over the secure path, and reports
// the satisfied state up so the gate can disable the build action until the project is ready.
export function ReadinessPanel({
  itemId,
  onChange,
}: {
  itemId: number;
  onChange: (snapshot: ReadinessSnapshot) => void;
}) {
  const navigate = useNavigation();
  const [view, setView] = useState<View>({ kind: 'loading' });
  const [busy, setBusy] = useState(false);
  const [provideFor, setProvideFor] = useState<ReadinessItem | null>(null);
  const [secret, setSecret] = useState('');
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const apply = useCallback(
    (assessment: ReadinessAssessment) => {
      setView({ kind: 'assessed', assessment });
      onChange({
        assessed: true,
        satisfied: assessment.satisfied,
        blocking: assessment.blocking_open,
      });
    },
    [onChange],
  );

  const load = useCallback(async () => {
    try {
      const result = await fetchReadiness(itemId);
      if (result === 'unassessed') {
        setView({ kind: 'unassessed' });
        onChange({ assessed: false, satisfied: false, blocking: [] });
      } else {
        apply(result);
      }
    } catch {
      setView({ kind: 'error' });
      onChange({ assessed: false, satisfied: false, blocking: [] });
    }
  }, [itemId, apply, onChange]);

  useEffect(() => {
    setView({ kind: 'loading' });
    void load();
  }, [load]);

  const run = useCallback(async () => {
    setBusy(true);
    setActionError(null);
    try {
      apply(await runReadiness(itemId));
    } catch {
      setActionError('The readiness check could not run. Check the Brain connection.');
    } finally {
      setBusy(false);
    }
  }, [itemId, apply]);

  const submitSecret = useCallback(async () => {
    if (!provideFor?.step_id) return;
    setBusy(true);
    setActionError(null);
    try {
      await provideCredential(provideFor.step_id, secret);
      setSecret('');
      setProvideFor(null);
      setConfirmOpen(false);
      await load();
    } catch {
      setActionError('The credential could not be provided. It was not stored.');
      setConfirmOpen(false);
    } finally {
      setBusy(false);
    }
  }, [provideFor, secret, load]);

  const header = (
    <div className="mb-3 flex items-center justify-between gap-2">
      <MonoLabel tone="accent">build readiness</MonoLabel>
      <OverflowMenu
        label="Readiness actions"
        items={[
          { label: view.kind === 'unassessed' ? 'Run check' : 'Re-run check', onClick: () => void run() },
          { label: 'Open approval queue', onClick: () => navigate('dashboard') },
        ]}
      />
    </div>
  );

  if (view.kind === 'loading') {
    return (
      <div className="rounded-glass border border-line bg-surface/40 p-4">
        {header}
        <p className="text-sm text-muted">Reading the readiness assessment…</p>
      </div>
    );
  }

  if (view.kind === 'error') {
    return (
      <div className="rounded-glass border border-line bg-surface/40 p-4">
        {header}
        <p className="text-sm text-muted">
          Readiness is unavailable. Check the Brain connection and try again.
        </p>
      </div>
    );
  }

  if (view.kind === 'unassessed') {
    return (
      <div className="rounded-glass border border-line bg-surface/40 p-4">
        {header}
        <p className="mb-3 text-sm text-muted">
          This project has not been assessed yet. Run the readiness check to see what it needs
          before it can build.
        </p>
        {actionError ? <p className="mb-2 text-xs text-danger">{actionError}</p> : null}
        <Button variant="primary" onClick={() => void run()} disabled={busy}>
          {busy ? 'Running' : 'Run readiness check'}
        </Button>
      </div>
    );
  }

  const { assessment } = view;
  const grouped = CATEGORIES.map((category) => ({
    ...category,
    items: assessment.items.filter((item) => item.category === category.key),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="rounded-glass border border-line bg-surface/40 p-4">
      {header}

      {/* The readiness satisfied indicator. */}
      <div
        className={[
          'mb-3 flex items-start gap-2 rounded-md border p-3',
          assessment.satisfied ? 'border-status-green' : 'border-electric',
        ].join(' ')}
      >
        <span className="mt-0.5">
          <StatusDot state={assessment.satisfied ? 'live' : 'gate'} />
        </span>
        <div className="text-sm">
          {assessment.satisfied ? (
            <p className="text-status-green">Ready to build. Every blocking item is resolved.</p>
          ) : (
            <>
              <p className="text-cream">
                Not ready to build. {assessment.blocking_open.length} blocking item
                {assessment.blocking_open.length === 1 ? '' : 's'} remain.
              </p>
              <p className="text-muted">{assessment.blocking_open.join(', ')}</p>
            </>
          )}
        </div>
      </div>

      {actionError ? <p className="mb-2 text-xs text-danger">{actionError}</p> : null}

      <div className="space-y-4">
        {grouped.map((group) => (
          <div key={group.key}>
            <div className="mb-2 flex items-center gap-2">
              <MonoLabel tone="faint">{group.label}</MonoLabel>
              <span className="mono-meta text-faint">{group.items.length}</span>
            </div>
            <ul className="space-y-2">
              {group.items.map((item) => (
                <li
                  key={item.step_id}
                  className="rounded-md border border-line/60 bg-black/10 p-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-2">
                      <span className="mt-1">
                        <StatusDot state={dotState(item)} label={stateLabel(item)} />
                      </span>
                      <div>
                        <p className="text-sm text-cream">{item.question ?? item.key}</p>
                        <p className="mono-meta text-faint">{stateLabel(item)}</p>
                      </div>
                    </div>
                    {item.blocking ? (
                      <Pill variant="accent">blocking</Pill>
                    ) : (
                      <Pill variant="grey">flag</Pill>
                    )}
                  </div>

                  {/* Blocking items route into the approval queue; credential items also provide. */}
                  {item.resolution === 'needs_user' ? (
                    <div className="mt-2">
                      <Button variant="outline" onClick={() => navigate('dashboard')}>
                        Answer in approval queue
                      </Button>
                    </div>
                  ) : null}

                  {item.resolution === 'needs_credential' ? (
                    <div className="mt-2 space-y-2">
                      {provideFor?.step_id === item.step_id ? (
                        <div className="space-y-2">
                          <label className="block">
                            <span className="mono-meta text-faint">
                              {item.provider ? `${item.provider} secret` : 'secret'}
                            </span>
                            <input
                              type="password"
                              autoComplete="off"
                              value={secret}
                              onChange={(event) => setSecret(event.target.value)}
                              placeholder="Paste the secret. It is sent securely and never shown again."
                              className="mt-1 w-full rounded-md border border-line bg-black/30 px-3 py-2 text-sm text-cream outline-none focus:border-accent"
                            />
                          </label>
                          <div className="flex flex-wrap gap-2">
                            <Button
                              variant="primary"
                              disabled={busy || !secret.trim()}
                              onClick={() => setConfirmOpen(true)}
                            >
                              Provide securely
                            </Button>
                            <Button
                              variant="muted"
                              disabled={busy}
                              onClick={() => {
                                setSecret('');
                                setProvideFor(null);
                              }}
                            >
                              Cancel
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          <Button
                            variant="outline"
                            onClick={() => {
                              setSecret('');
                              setProvideFor(item);
                            }}
                          >
                            Provide credential
                          </Button>
                          <Button variant="muted" onClick={() => navigate('dashboard')}>
                            Open approval queue
                          </Button>
                        </div>
                      )}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title="Provide credential"
        body={
          provideFor?.provider
            ? `Send the ${provideFor.provider} secret to the Brain secure store? It is never shown, logged, or kept in this app.`
            : 'Send the secret to the Brain secure store? It is never shown, logged, or kept in this app.'
        }
        confirmLabel="Provide securely"
        busy={busy}
        onConfirm={() => void submitSecret()}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
