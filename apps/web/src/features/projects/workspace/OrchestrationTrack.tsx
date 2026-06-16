import { Fragment } from 'react';

import { StatusDot } from '../../../components/primitives';
import { STEP_DOT } from './runtimeApi';
import type { Step } from './runtimeApi';

// A StageTrack-style walk of a run's task graph: one focusable node per step in seq order, each
// carrying its own status colour, connected by the same dotted rule the StageTrack primitive
// uses. Built from the shared StatusDot and MonoLabel primitives so the brand orange is never
// borrowed for a status it does not own. Every node names its task and state for assistive tech
// and is keyboard reachable; selecting one scrolls its full step into view.
export function OrchestrationTrack({
  steps,
  onSelect,
}: {
  steps: Step[];
  onSelect?: (stepId: number) => void;
}) {
  if (steps.length === 0) return null;

  return (
    <div
      role="list"
      aria-label="Orchestration task graph"
      className="scroll-themed flex items-start gap-1 overflow-x-auto pb-1"
    >
      {steps.map((step, index) => {
        const state = STEP_DOT[step.status] ?? 'pending';
        const label = step.title || step.kind;
        const description = `Task ${step.seq}: ${label}, ${step.status.replace(/_/g, ' ')}`;
        return (
          <Fragment key={step.id}>
            <button
              type="button"
              role="listitem"
              aria-label={description}
              title={description}
              onClick={onSelect ? () => onSelect(step.id) : undefined}
              className="flex shrink-0 flex-col items-center gap-1 rounded-md px-1 py-1 text-center outline-none focus-visible:ring-1 focus-visible:ring-accent"
            >
              <StatusDot state={state} label={step.status} />
              <span className="font-mono text-[0.55rem] uppercase tracking-[0.08em] text-faint">
                #{step.seq}
              </span>
              <span className="max-w-[5.5rem] truncate text-[0.6rem] text-muted">{label}</span>
            </button>
            {index < steps.length - 1 ? (
              <span
                aria-hidden
                className="mt-[0.3rem] h-px w-5 shrink-0 border-t border-dotted border-line"
              />
            ) : null}
          </Fragment>
        );
      })}
    </div>
  );
}
