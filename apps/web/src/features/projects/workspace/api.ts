// Typed Brain calls for the per project workspace. Each wraps the generated client and
// returns the validated payload or throws, so the tab components stay declarative.

import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../../app/client';

export type Overview = Schemas['ProjectOverview'];
export type FilesResponse = Schemas['FilesResponse'];
export type FileNode = Schemas['FileNode'];
export type FileContent = Schemas['FileContent'];
export type BuildLogEntry = Schemas['BuildLogRead'];
export type ProjectUpdate = Schemas['ProjectUpdateRead'];
export type EditorProposal = Schemas['EditorProposal'];
export type EditorApplyResponse = Schemas['EditorApplyResponse'];
export type RollbackResponse = Schemas['RollbackResponse'];

export async function getOverview(projectId: number): Promise<Overview> {
  const { data, error } = await api.GET('/projects/{project_id}/overview', {
    params: { path: { project_id: projectId } },
  });
  if (error || !data) throw new Error('could not load overview');
  return data as Overview;
}

export async function getFiles(projectId: number): Promise<FilesResponse> {
  const { data, error } = await api.GET('/projects/{project_id}/files', {
    params: { path: { project_id: projectId } },
  });
  if (error || !data) throw new Error('could not load files');
  return data as FilesResponse;
}

export async function getFileContent(projectId: number, path: string): Promise<FileContent> {
  const { data, error } = await api.GET('/projects/{project_id}/files/content', {
    params: { path: { project_id: projectId }, query: { path } },
  });
  if (error || !data) throw new Error('could not load file');
  return data as FileContent;
}

export async function deleteFile(projectId: number, path: string): Promise<void> {
  const { error } = await api.DELETE('/projects/{project_id}/files', {
    params: { path: { project_id: projectId }, query: { path } },
  });
  if (error) throw new Error('could not delete file');
}

export async function getBuildLog(projectId: number): Promise<BuildLogEntry[]> {
  const { data, error } = await api.GET('/projects/{project_id}/build-log', {
    params: { path: { project_id: projectId } },
  });
  if (error || !data) throw new Error('could not load build log');
  return data as BuildLogEntry[];
}

export async function getUpdates(projectId: number): Promise<ProjectUpdate[]> {
  const { data, error } = await api.GET('/projects/{project_id}/updates', {
    params: { path: { project_id: projectId } },
  });
  if (error || !data) throw new Error('could not load update logs');
  return data as ProjectUpdate[];
}

export async function proposeEdit(
  projectId: number,
  filePath: string,
  instruction: string,
): Promise<EditorProposal> {
  const { data, error } = await api.POST('/projects/{project_id}/editor/propose', {
    params: { path: { project_id: projectId } },
    body: { file_path: filePath, instruction },
  });
  if (error || !data) throw new Error('the editor could not propose a change');
  return data as EditorProposal;
}

export async function applyEdit(
  projectId: number,
  proposalId: number,
): Promise<EditorApplyResponse> {
  // approved is always true here: the UI only calls apply after the explicit Approve gate.
  const { data, error } = await api.POST('/projects/{project_id}/editor/apply', {
    params: { path: { project_id: projectId } },
    body: { proposal_id: proposalId, approved: true },
  });
  if (error || !data) throw new Error('apply failed');
  return data as EditorApplyResponse;
}

export async function rollbackEdit(
  projectId: number,
  buildLogId: number,
): Promise<RollbackResponse> {
  const { data, error } = await api.POST('/projects/{project_id}/editor/rollback', {
    params: { path: { project_id: projectId } },
    body: { build_log_id: buildLogId },
  });
  if (error || !data) throw new Error('rollback failed');
  return data as RollbackResponse;
}
