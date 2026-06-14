// Typed Brain calls for the agent runtime, plus the pure derivation that turns a project's runs
// and steps into the agents acting on it. The runtime is read only: there are no writers here,
// only projections of the ledger the Brain authored.

import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../../app/client';

export type Run = Schemas['RunRead'];
export type RunWithSteps = Schemas['RunWithSteps'];
export type Step = Schemas['StepRead'];

// The four states that mean a step has come to rest. Anything else is still in flight and worth
// re-reading on the next poll.
export const TERMINAL_STATUSES = new Set([
  'completed_verified',
  'completed_unverified',
  'failed',
  'skipped',
]);

// Kinds whose work is reasoning, not action: they legitimately have nothing for a tool to
// verify, so an unverified completion reads as neutral rather than a warning.
export const NEUTRAL_KINDS = new Set(['think', 'plan', 'note', 'summary', 'reason', 'decide']);

export async function listRuns(projectId: number): Promise<Run[]> {
  const { data, error } = await api.GET('/runtime/runs', {
    params: { query: { project_id: projectId } },
  });
  if (error || !data) throw new Error('could not load runs');
  return data as Run[];
}

export async function getRun(runId: number): Promise<RunWithSteps> {
  const { data, error } = await api.GET('/runtime/runs/{run_id}', {
    params: { path: { run_id: runId } },
  });
  if (error || !data) throw new Error('could not load run');
  return data as RunWithSteps;
}

// Steps with seq beyond the cursor step. When after is null the Brain falls back to the run's
// own cursor_step_id, returning the unsettled tail (and any newly proposed steps).
export async function getStepsAfter(runId: number, after: number | null): Promise<Step[]> {
  const { data, error } = await api.GET('/runtime/runs/{run_id}/steps', {
    params: {
      path: { run_id: runId },
      query: after != null ? { after } : {},
    },
  });
  if (error || !data) throw new Error('could not load steps');
  return data as Step[];
}

// The largest leading run of settled steps; its id is the live cursor we poll past. Assumes
// steps are in seq order.
export function settledBoundary(steps: Step[]): number | null {
  let boundary: number | null = null;
  for (const step of steps) {
    if (!TERMINAL_STATUSES.has(step.status)) break;
    boundary = step.id;
  }
  return boundary;
}

// Merge a freshly polled tail into the known steps: updated steps overwrite, new steps append.
export function mergeSteps(current: Step[], tail: Step[]): Step[] {
  const byId = new Map<number, Step>();
  for (const step of current) byId.set(step.id, step);
  for (const step of tail) byId.set(step.id, step);
  return [...byId.values()].sort((a, b) => a.seq - b.seq);
}

// The run roll-up shown on the live header, mirroring the Brain's derivation so the header stays
// consistent with the steps on screen between full reloads.
export function deriveRunStatus(steps: Step[]): string {
  const set = new Set(steps.map((step) => step.status));
  if (set.size === 0) return 'planned';
  if (set.has('executing')) return 'executing';
  if (set.has('waiting_approval')) return 'waiting_approval';
  if (set.has('blocked')) return 'blocked';
  if (set.has('planned')) return 'planned';
  if (set.has('failed')) return 'failed';
  return 'completed';
}

function toolEvidenceCount(step: Step): number {
  return (step.evidence ?? []).filter(
    (item) => (item as { source?: string }).source === 'tool',
  ).length;
}

export interface DerivedAgent {
  actor: string; // the step's proposed_by: the agent that authored the work
  steps: number;
  verified: number;
  unverified: number;
  failed: number;
  active: number; // steps not yet at rest
  toolEvidence: number;
}

// Derive the agents on a project from the runtime ledger, never from the build log. An agent is
// a distinct actor (a step's proposed_by) seen across the project's steps, with its real tallies.
export function deriveAgents(steps: Step[]): DerivedAgent[] {
  const byActor = new Map<string, DerivedAgent>();
  for (const step of steps) {
    const actor = step.proposed_by || 'unknown';
    const agent =
      byActor.get(actor) ??
      { actor, steps: 0, verified: 0, unverified: 0, failed: 0, active: 0, toolEvidence: 0 };
    agent.steps += 1;
    if (step.status === 'completed_verified') agent.verified += 1;
    else if (step.status === 'completed_unverified') agent.unverified += 1;
    else if (step.status === 'failed') agent.failed += 1;
    if (!TERMINAL_STATUSES.has(step.status)) agent.active += 1;
    agent.toolEvidence += toolEvidenceCount(step);
    byActor.set(actor, agent);
  }
  return [...byActor.values()].sort((a, b) => b.steps - a.steps);
}
