// The read model behind the agent activity surface. It projects the runtime ledger (runs and
// their steps) into one row per recent build run, deriving the observability dimensions the
// surface shows: backend, task, effective autonomy, gate decision, status, cost and tokens, and
// timing. Read only: there are no writers here, only projections of what the Brain authored.
//
// Several dimensions are not first class columns on a run; they are recovered tolerantly from the
// plan blob and the step evidence. When the ledger never recorded a figure (cost or tokens on a
// run that predates usage accounting, say), the row says so plainly rather than inventing a zero.

import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../../app/client';
import { getRun } from '../workspace/runtimeApi';

type Run = Schemas['RunRead'];
type RunWithSteps = Schemas['RunWithSteps'];
type Step = Schemas['StepRead'];
type Project = Schemas['ProjectRead'];

// How many of the most recent runs the surface reads steps for. A long lived workspace would
// otherwise fan out into an unbounded number of detail requests. When more runs exist the surface
// says it is showing the most recent window.
export const ACTIVITY_RUN_CAP = 30;

export type GateDecision =
  | 'awaiting'
  | 'approved'
  | 'rejected'
  | 'autonomous'
  | 'gated';

export interface AutonomyView {
  level: number;
  // The effective mode the runtime honors today: level 0 gates every step, any non-zero level
  // runs without forcing the gate. The stored level is kept for the detail.
  mode: 'supervised' | 'autonomous';
}

export interface UsageView {
  // Null means the ledger recorded no figure, distinct from a real zero.
  tokens: number | null;
  costUsd: number | null;
}

export interface AgentRunRow {
  runId: number;
  projectId: number | null;
  projectName: string;
  backend: string;
  task: string;
  autonomy: AutonomyView;
  gate: GateDecision;
  status: string;
  usage: UsageView;
  createdAt: string;
  finishedAt: string | null;
  // Milliseconds from created to finished, or null while the run is still open.
  durationMs: number | null;
  stepCount: number;
}

export interface AgentActivity {
  rows: AgentRunRow[];
  capped: boolean;
}

async function listAllRuns(): Promise<Run[]> {
  const { data } = await api.GET('/runtime/runs');
  return (data as Run[]) ?? [];
}

async function projectNames(): Promise<Map<number, string>> {
  const { data } = await api.GET('/projects');
  const map = new Map<number, string>();
  for (const project of (data as Project[]) ?? []) map.set(project.id, project.name);
  return map;
}

function nameFor(projectId: number | null, names: Map<number, string>): string {
  if (projectId == null) return 'no project';
  return names.get(projectId) ?? `project ${projectId}`;
}

function stringFrom(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

// The execution backend behind a run. Recorded explicitly on the plan when the executor wrote it,
// otherwise the run kind is the honest fallback (general, executor, readiness).
export function deriveBackend(run: Run): string {
  const plan = run.plan as Record<string, unknown>;
  return (
    stringFrom(plan.backend) ??
    stringFrom(plan.runner) ??
    stringFrom(plan.executor) ??
    stringFrom(plan.model) ??
    run.kind
  );
}

export function deriveTask(run: Run): string {
  const plan = run.plan as Record<string, unknown>;
  return run.goal_summary.trim() || stringFrom(plan.task) || stringFrom(plan.title) || 'untitled run';
}

export function deriveAutonomy(run: Run): AutonomyView {
  return {
    level: run.autonomy_level,
    mode: run.autonomy_level === 0 ? 'supervised' : 'autonomous',
  };
}

// The gate verdict for a run, read from the steps' approval resolutions. A run still parked at the
// gate is awaiting; a rejection anywhere outranks an approval; a non-zero autonomy run that never
// hit the gate ran autonomously; a supervised run with no decision yet is simply gated.
export function deriveGate(run: Run, steps: Step[]): GateDecision {
  if (run.status === 'waiting_approval') return 'awaiting';
  let approved = false;
  for (const step of steps) {
    const resolution = stringFrom((step.approval as Record<string, unknown> | null)?.resolution);
    if (resolution === 'rejected') return 'rejected';
    if (resolution === 'approved') approved = true;
  }
  if (approved) return 'approved';
  return run.autonomy_level === 0 ? 'gated' : 'autonomous';
}

const TOKEN_KEYS = [
  'total_tokens',
  'tokens',
  'token_count',
  'prompt_tokens',
  'completion_tokens',
  'input_tokens',
  'output_tokens',
];
const COST_KEYS = ['cost_usd', 'cost', 'total_cost', 'usd'];

function readNumber(source: Record<string, unknown>, keys: string[]): number | null {
  let found: number | null = null;
  for (const key of keys) {
    const value = source[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      found = (found ?? 0) + value;
    }
  }
  return found;
}

// Tokens and cost a step recorded, looked for on the tool call and on every evidence item, and on
// a nested usage object where a provider response stashed them. Returns null for a figure the step
// never recorded so the caller can keep not recorded distinct from zero.
function stepUsage(step: Step): UsageView {
  let tokens: number | null = null;
  let costUsd: number | null = null;

  const sources: Record<string, unknown>[] = [];
  if (step.tool_call) sources.push(step.tool_call as Record<string, unknown>);
  for (const item of (step.evidence ?? []) as Record<string, unknown>[]) {
    sources.push(item);
    if (item.usage && typeof item.usage === 'object') {
      sources.push(item.usage as Record<string, unknown>);
    }
  }

  for (const source of sources) {
    const t = readNumber(source, TOKEN_KEYS);
    if (t != null) tokens = (tokens ?? 0) + t;
    const c = readNumber(source, COST_KEYS);
    if (c != null) costUsd = (costUsd ?? 0) + c;
  }
  return { tokens, costUsd };
}

export function deriveUsage(steps: Step[]): UsageView {
  let tokens: number | null = null;
  let costUsd: number | null = null;
  for (const step of steps) {
    const usage = stepUsage(step);
    if (usage.tokens != null) tokens = (tokens ?? 0) + usage.tokens;
    if (usage.costUsd != null) costUsd = (costUsd ?? 0) + usage.costUsd;
  }
  return { tokens, costUsd };
}

function durationMs(createdAt: string, finishedAt: string | null): number | null {
  if (!finishedAt) return null;
  const start = new Date(createdAt).getTime();
  const end = new Date(finishedAt).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null;
  return end - start;
}

export function deriveRow(run: RunWithSteps, names: Map<number, string>): AgentRunRow {
  const steps = run.steps;
  return {
    runId: run.id,
    projectId: run.project_id,
    projectName: nameFor(run.project_id, names),
    backend: deriveBackend(run),
    task: deriveTask(run),
    autonomy: deriveAutonomy(run),
    gate: deriveGate(run, steps),
    status: run.status,
    usage: deriveUsage(steps),
    createdAt: run.created_at,
    finishedAt: run.finished_at,
    durationMs: durationMs(run.created_at, run.finished_at),
    stepCount: steps.length,
  };
}

// The recent build runs across every project, newest first, each projected into its row. Capped at
// the most recent window so the surface stays bounded on a long lived workspace.
export async function loadAgentActivity(): Promise<AgentActivity> {
  const [runs, names] = await Promise.all([listAllRuns(), projectNames()]);
  const ordered = [...runs].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
  const recent = ordered.slice(0, ACTIVITY_RUN_CAP);
  const detailed = await Promise.all(recent.map((run) => getRun(run.id)));
  return {
    rows: detailed.map((run) => deriveRow(run, names)),
    capped: runs.length > ACTIVITY_RUN_CAP,
  };
}

// Compact human figures for the row cells. Kept here so the view stays declarative.
export function formatTokens(tokens: number | null): string {
  if (tokens == null) return 'not recorded';
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(tokens >= 100000 ? 0 : 1)}k`;
  return String(tokens);
}

export function formatCost(costUsd: number | null): string {
  if (costUsd == null) return 'not recorded';
  if (costUsd === 0) return '$0.00';
  if (costUsd < 0.01) return '<$0.01';
  return `$${costUsd.toFixed(2)}`;
}

export function formatDuration(ms: number | null): string {
  if (ms == null) return 'in flight';
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}
