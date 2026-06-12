import { useEffect, useState } from 'react';

import { Button, GlassCard, MonoLabel, Modal, Pill } from '../../../components/primitives';
import { useFlow } from '../FlowProvider';
import type { ClarifyResponse } from '../FlowProvider';

// Shows gap closing questions and selectable integration chips, an Open preview modal, and
// a continue action that posts the answers, selected integrations, and scope changes.
export function ClarifyCard() {
  const { selected, getClarify, submitClarify, getPreview } = useFlow();
  const [data, setData] = useState<ClarifyResponse | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const planReady = Boolean(selected?.plan_available);
  const itemId = selected?.id;

  useEffect(() => {
    setData(null);
    setAnswers({});
    setSelectedIds([]);
    if (!itemId || !planReady) return;
    let cancelled = false;
    void getClarify(itemId)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch(() => {
        if (!cancelled) setError('Could not load clarify.');
      });
    return () => {
      cancelled = true;
    };
  }, [itemId, planReady, getClarify]);

  if (!selected || selected.route !== 'project') {
    return (
      <GlassCard>
        <MonoLabel tone="accent">clarify</MonoLabel>
        <p className="mt-2 text-sm text-muted">Clarify applies to project shaped items.</p>
      </GlassCard>
    );
  }

  if (!planReady) {
    return (
      <GlassCard>
        <MonoLabel tone="accent">clarify</MonoLabel>
        <p className="mt-2 text-sm text-muted">Run Process first to generate the plan.</p>
      </GlassCard>
    );
  }

  function toggle(id: number | null) {
    if (id === null) return;
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((entry) => entry !== id) : [...current, id],
    );
  }

  async function onContinue() {
    if (!itemId) return;
    setBusy(true);
    setError(null);
    try {
      await submitClarify(itemId, {
        answers,
        selected_integration_ids: selectedIds,
        scope_changes: {},
      });
    } catch {
      setError('Could not submit clarify.');
    } finally {
      setBusy(false);
    }
  }

  async function openPreview() {
    if (!itemId) return;
    setPreview(await getPreview(itemId));
  }

  return (
    <GlassCard active={Boolean(selected.preview_available)}>
      <div className="mb-3 flex items-center justify-between">
        <MonoLabel tone="accent">clarify</MonoLabel>
      </div>

      <div className="mb-3 space-y-2">
        {(data?.clarifying_questions ?? []).map((question) => (
          <div key={question}>
            <label className="mono-label mb-1 block text-faint">{question}</label>
            <input
              value={answers[question] ?? ''}
              onChange={(event) =>
                setAnswers((current) => ({ ...current, [question]: event.target.value }))
              }
              className="w-full rounded-lg border border-line bg-canvas px-3 py-1.5 text-sm text-cream outline-none focus:border-accent"
            />
          </div>
        ))}
        {data && data.clarifying_questions.length === 0 ? (
          <p className="text-sm text-muted">No open questions.</p>
        ) : null}
      </div>

      <MonoLabel tone="faint" className="mb-1 block">
        integrations
      </MonoLabel>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {(data?.suggested_integrations ?? []).map((integration) => {
          const integrationId = integration.integration_id ?? null;
          const isSelected = integrationId !== null && selectedIds.includes(integrationId);
          return (
            <button
              key={integration.provider}
              type="button"
              onClick={() => toggle(integrationId)}
              disabled={integrationId === null}
            >
              <Pill variant={isSelected ? 'solid' : integration.status === 'connected' ? 'green' : 'grey'}>
                {integration.provider}
              </Pill>
            </button>
          );
        })}
      </div>

      {error ? <p className="mb-2 text-xs text-danger">{error}</p> : null}

      <div className="flex flex-wrap gap-2">
        {selected.preview_available ? (
          <Button variant="outline" onClick={() => void openPreview()}>
            Open preview
          </Button>
        ) : null}
        <Button variant="primary" onClick={() => void onContinue()} disabled={busy}>
          {busy ? 'Saving' : 'Continue'}
        </Button>
      </div>

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
