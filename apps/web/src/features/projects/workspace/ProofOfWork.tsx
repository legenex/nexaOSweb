import { useState } from 'react';

import { MonoLabel, Pill, StatusDot } from '../../../components/primitives';
import { NEUTRAL_KINDS } from './runtimeApi';
import type { Step } from './runtimeApi';

// The verification verdict, made unmissable. A verified completion is green, an unverified one
// is an amber warning, and a completion whose kind is reasoning (think, plan) reads neutral,
// because it legitimately had nothing for a tool to verify.
export function VerificationBadge({ step }: { step: Step }) {
  if (step.status === 'completed_verified') {
    return (
      <span className="inline-flex items-center gap-1">
        <StatusDot state="live" label="verified" />
        <Pill variant="green">verified</Pill>
      </span>
    );
  }
  if (step.status === 'completed_unverified') {
    if (NEUTRAL_KINDS.has(step.kind)) {
      return (
        <span className="inline-flex items-center gap-1">
          <StatusDot state="pending" label="nothing to verify" />
          <Pill variant="grey">no verification needed</Pill>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1">
        <StatusDot state="warn" label="unverified" />
        <Pill variant="solid">unverified</Pill>
      </span>
    );
  }
  return null;
}

function evidenceLabel(item: Record<string, unknown>): string {
  const source = typeof item.source === 'string' ? item.source : 'unknown';
  if (source === 'tool') {
    const action = item.action ?? item.command ?? item.name ?? item.endpoint;
    return action ? `tool · ${String(action)}` : 'tool';
  }
  return source;
}

// A compact, readable view of one evidence item: its source, a stored-output reference when the
// content was spilled to the runtime root, and otherwise its inline detail.
function EvidenceItem({ item }: { item: Record<string, unknown> }) {
  const source = typeof item.source === 'string' ? item.source : 'unknown';
  const ref = typeof item.content_ref === 'string' ? item.content_ref : null;
  const preview = typeof item.content_preview === 'string' ? item.content_preview : null;
  const bytes = typeof item.content_bytes === 'number' ? item.content_bytes : null;
  // Everything beyond the bookkeeping keys is the item's own detail.
  const detail = Object.fromEntries(
    Object.entries(item).filter(
      ([key]) =>
        !['source', 'content', 'content_ref', 'content_preview', 'content_bytes'].includes(key),
    ),
  );
  const hasDetail = Object.keys(detail).length > 0;

  return (
    <li className="rounded-lg border border-line bg-black/20 p-2">
      <div className="flex flex-wrap items-center gap-2">
        <StatusDot state={source === 'tool' ? 'live' : 'pending'} label={source} />
        <MonoLabel tone={source === 'tool' ? 'accent' : 'faint'}>{evidenceLabel(item)}</MonoLabel>
        {ref ? (
          <MonoLabel tone="faint">
            stored output{bytes != null ? ` · ${bytes} bytes` : ''}
          </MonoLabel>
        ) : null}
      </div>
      {hasDetail ? (
        <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words font-mono text-[0.7rem] text-muted">
          {JSON.stringify(detail, null, 2)}
        </pre>
      ) : null}
      {preview ? (
        <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words font-mono text-[0.7rem] text-muted">
          {preview}
          {bytes != null ? '\n… (truncated, full output stored by reference)' : ''}
        </pre>
      ) : null}
    </li>
  );
}

// The proof of work behind a step: its tool call and the evidence summary. Collapsible, and
// expanded by default on a failed step so the failure is visible without a click.
export function ProofOfWork({ step }: { step: Step }) {
  const failed = step.status === 'failed';
  const [open, setOpen] = useState(failed);

  const evidence = (step.evidence ?? []) as Record<string, unknown>[];
  const toolCall = step.tool_call as Record<string, unknown> | null;
  const toolEvidence = evidence.filter((item) => item.source === 'tool').length;

  // A step that ran no tool and produced no evidence has no proof to show; say so plainly.
  const hasProof = evidence.length > 0 || toolCall != null || step.failure != null;

  return (
    <div className="mt-2 rounded-lg border border-line bg-surface/40">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <span className="text-muted">{open ? '▾' : '▸'}</span>
        <MonoLabel tone="accent">proof of work</MonoLabel>
        <span className="ml-auto flex items-center gap-2">
          <MonoLabel tone="faint">
            {evidence.length} evidence
            {toolEvidence > 0 ? ` · ${toolEvidence} tool` : ''}
          </MonoLabel>
        </span>
      </button>

      {open ? (
        <div className="space-y-3 border-t border-line px-3 py-3">
          {!hasProof ? (
            <p className="text-xs text-muted">
              No tool ran and no evidence was recorded for this step.
            </p>
          ) : null}

          {toolCall ? (
            <div>
              <MonoLabel tone="faint" className="mb-1 block">
                tool call
              </MonoLabel>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line bg-black/30 p-2 font-mono text-[0.7rem] text-muted">
                {JSON.stringify(toolCall, null, 2)}
              </pre>
            </div>
          ) : null}

          {step.failure ? (
            <div>
              <MonoLabel tone="faint" className="mb-1 block">
                failure
              </MonoLabel>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-danger/40 bg-black/30 p-2 font-mono text-[0.7rem] text-danger">
                {JSON.stringify(step.failure, null, 2)}
              </pre>
            </div>
          ) : null}

          {evidence.length > 0 ? (
            <div>
              <MonoLabel tone="faint" className="mb-1 block">
                evidence
              </MonoLabel>
              <ul className="space-y-2">
                {evidence.map((item, index) => (
                  <EvidenceItem key={index} item={item} />
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
