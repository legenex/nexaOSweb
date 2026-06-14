// Build readiness reads and the two writes the gate panel needs: run an assessment, and provide
// a credential for a blocking item. The secret goes straight to the secure endpoint and is never
// kept here. Everything else about the runtime stays read only and flows through the typed client.

import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';

export type ReadinessAssessment = Schemas['ReadinessAssessment'];
export type ReadinessItem = Schemas['ReadinessItem'];

// The latest assessment for an item's project, or the literal 'unassessed' when the project has
// never been assessed (the Brain answers 404), so the panel shows an honest not yet run state.
export async function fetchReadiness(
  itemId: number,
): Promise<ReadinessAssessment | 'unassessed'> {
  const { data, error, response } = await api.GET('/flow/items/{item_id}/readiness', {
    params: { path: { item_id: itemId } },
  });
  if (response.status === 404) return 'unassessed';
  if (error || !data) throw new Error('readiness read failed');
  return data as ReadinessAssessment;
}

// Run the assessment at the Human Gate. Returns the fresh result.
export async function runReadiness(itemId: number): Promise<ReadinessAssessment> {
  const { data, error } = await api.POST('/flow/items/{item_id}/readiness', {
    params: { path: { item_id: itemId } },
  });
  if (error || !data) throw new Error('readiness evaluation failed');
  return data as ReadinessAssessment;
}

// Provide the secret for a blocking credential item. The value is posted to the secure endpoint
// and never returned, logged, or stored in the web app.
export async function provideCredential(stepId: number, secret: string): Promise<void> {
  const { error } = await api.POST('/integrations/credentials/fulfil', {
    body: { step_id: stepId, secret },
  });
  if (error) throw new Error('credential submission failed');
}
