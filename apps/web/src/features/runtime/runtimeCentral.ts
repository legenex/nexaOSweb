// Central, cross-project runtime reads for the approval queue and the failure view, plus the
// single human gate write (resolve). The runtime is otherwise read only.

import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';

export type Run = Schemas['RunRead'];
export type ApprovalRequest = Schemas['ApprovalRequest'];
export type Step = Schemas['StepRead'];
type Project = Schemas['ProjectRead'];

export interface QueueItem {
  approval: ApprovalRequest;
  runId: number;
  projectId: number | null;
  projectName: string;
}

export interface FailureItem {
  step: Step;
  runId: number;
  projectId: number | null;
  projectName: string;
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

// Every waiting_approval step across all runs, sorted by risk (material first) then age (oldest
// first), so the most consequential and longest waiting decisions surface at the top.
export async function loadApprovalQueue(): Promise<QueueItem[]> {
  const [runs, names] = await Promise.all([listAllRuns(), projectNames()]);
  const gatedRuns = runs.filter((run) => run.status === 'waiting_approval');
  const lists = await Promise.all(
    gatedRuns.map((run) =>
      api
        .GET('/runtime/runs/{run_id}/approvals', { params: { path: { run_id: run.id } } })
        .then((res) => ({ run, approvals: (res.data as ApprovalRequest[]) ?? [] })),
    ),
  );
  const items: QueueItem[] = [];
  for (const { run, approvals } of lists) {
    for (const approval of approvals) {
      items.push({
        approval,
        runId: run.id,
        projectId: run.project_id,
        projectName: nameFor(run.project_id, names),
      });
    }
  }
  items.sort((a, b) => {
    const ra = a.approval.materially_affects ? 1 : 0;
    const rb = b.approval.materially_affects ? 1 : 0;
    if (ra !== rb) return rb - ra; // material first
    return (
      new Date(a.approval.created_at).getTime() - new Date(b.approval.created_at).getTime()
    ); // then oldest first
  });
  return items;
}

export async function resolveStep(
  stepId: number,
  resolution: 'approved' | 'rejected',
  note = '',
): Promise<void> {
  const { error } = await api.POST('/runtime/steps/{step_id}/resolve', {
    params: { path: { step_id: stepId } },
    body: { resolution, note },
  });
  if (error) throw new Error('resolve failed');
}

// Every failed step across all runs, newest first, with its run and project for the back links.
export async function loadFailures(): Promise<FailureItem[]> {
  const [runs, names] = await Promise.all([listAllRuns(), projectNames()]);
  const lists = await Promise.all(
    runs.map((run) =>
      api
        .GET('/runtime/runs/{run_id}/failed', { params: { path: { run_id: run.id } } })
        .then((res) => ({ run, steps: (res.data as Step[]) ?? [] })),
    ),
  );
  const items: FailureItem[] = [];
  for (const { run, steps } of lists) {
    for (const step of steps) {
      items.push({
        step,
        runId: run.id,
        projectId: run.project_id,
        projectName: nameFor(run.project_id, names),
      });
    }
  }
  items.sort(
    (a, b) => new Date(b.step.updated_at).getTime() - new Date(a.step.updated_at).getTime(),
  );
  return items;
}
