// Flow data store. Holds the list of flow items, the selected run, and the actions the
// stage cards call. JSON endpoints go through the typed client; multipart capture and the
// markdown and html streams go through the raw transport.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import type { ReactNode } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { apiFetch, apiJson } from '../../app/api';
import { api } from '../../app/client';

export type FlowItem = Schemas['FlowItemDTO'];
export type InboxItem = Schemas['InboxItemRead'];
export type ClarifyResponse = Schemas['ClarifyResponse'];
export type ClarifyRequest = Schemas['ClarifyRequest'];
export type Project = Schemas['ProjectRead'];

export interface CaptureInput {
  name: string;
  body: string;
  source: string;
  file?: File | null;
}

interface FlowState {
  items: FlowItem[];
  selected: FlowItem | null;
  selectedId: number | null;
  loadingList: boolean;
  refresh: () => Promise<void>;
  select: (id: number) => Promise<void>;
  capture: (input: CaptureInput) => Promise<InboxItem>;
  expand: (name: string, body: string) => Promise<string>;
  process: (id: number) => Promise<void>;
  getPlan: (id: number) => Promise<string>;
  getClarify: (id: number) => Promise<ClarifyResponse>;
  submitClarify: (id: number, payload: ClarifyRequest) => Promise<void>;
  getPreview: (id: number) => Promise<string>;
  projects: Project[];
  refreshProjects: () => Promise<void>;
  approve: (projectId: number) => Promise<void>;
  reject: (projectId: number, reason: string) => Promise<void>;
  promote: (itemId: number) => Promise<void>;
}

const FlowContext = createContext<FlowState | null>(null);

export function FlowProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<FlowItem[]>([]);
  const [selected, setSelected] = useState<FlowItem | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);

  const select = useCallback(async (id: number) => {
    setSelectedId(id);
    const { data } = await api.GET('/flow/items/{item_id}', {
      params: { path: { item_id: id } },
    });
    if (data) setSelected(data as FlowItem);
  }, []);

  const refresh = useCallback(async () => {
    setLoadingList(true);
    try {
      const { data } = await api.GET('/flow/items', { params: { query: { limit: 50, offset: 0 } } });
      const list = (data as FlowItem[]) ?? [];
      setItems(list);
      if (list.length > 0) {
        const stillThere = list.find((entry) => entry.id === selectedId);
        await select((stillThere ?? list[0]!).id);
      } else {
        setSelected(null);
        setSelectedId(null);
      }
    } finally {
      setLoadingList(false);
    }
  }, [select, selectedId]);

  const capture = useCallback(
    async (input: CaptureInput) => {
      const form = new FormData();
      form.append('name', input.name);
      form.append('body', input.body);
      form.append('source', input.source);
      if (input.file) form.append('file', input.file);
      const response = await apiFetch('/intake/capture', { method: 'POST', body: form });
      if (!response.ok) throw new Error('capture failed');
      const created = (await response.json()) as InboxItem;
      await refresh();
      await select(created.id);
      return created;
    },
    [refresh, select],
  );

  const expand = useCallback(async (name: string, body: string) => {
    const result = await apiJson<{ expanded: string }>('/intake/expand', {
      method: 'POST',
      body: JSON.stringify({ name, body }),
    });
    return result.expanded;
  }, []);

  const process = useCallback(
    async (id: number) => {
      const { error } = await api.POST('/flow/items/{item_id}/process', {
        params: { path: { item_id: id } },
      });
      if (error) throw new Error('process failed');
      await select(id);
    },
    [select],
  );

  const getPlan = useCallback(async (id: number) => {
    const response = await apiFetch(`/flow/items/${id}/plan`);
    return response.ok ? response.text() : '';
  }, []);

  const getClarify = useCallback(async (id: number) => {
    const { data, error } = await api.GET('/flow/items/{item_id}/clarify', {
      params: { path: { item_id: id } },
    });
    if (error || !data) throw new Error('clarify failed');
    return data as ClarifyResponse;
  }, []);

  const submitClarify = useCallback(
    async (id: number, payload: ClarifyRequest) => {
      const { error } = await api.POST('/flow/items/{item_id}/clarify', {
        params: { path: { item_id: id } },
        body: payload,
      });
      if (error) throw new Error('clarify submit failed');
      await select(id);
    },
    [select],
  );

  const getPreview = useCallback(async (id: number) => {
    const response = await apiFetch(`/flow/items/${id}/preview`);
    return response.ok ? response.text() : '';
  }, []);

  const refreshProjects = useCallback(async () => {
    const { data } = await api.GET('/projects');
    setProjects((data as Project[]) ?? []);
  }, []);

  const reselect = useCallback(async () => {
    if (selectedId !== null) await select(selectedId);
    await refreshProjects();
  }, [selectedId, select, refreshProjects]);

  const approve = useCallback(
    async (projectId: number) => {
      const { error } = await api.POST('/projects/{project_id}/approve', {
        params: { path: { project_id: projectId } },
      });
      if (error) throw new Error('approve failed');
      await reselect();
    },
    [reselect],
  );

  const reject = useCallback(
    async (projectId: number, reason: string) => {
      const { error } = await api.POST('/projects/{project_id}/reject', {
        params: { path: { project_id: projectId } },
        body: { reason },
      });
      if (error) throw new Error('reject failed');
      await reselect();
    },
    [reselect],
  );

  const promote = useCallback(
    async (itemId: number) => {
      const { error } = await api.POST('/flow/items/{item_id}/promote', {
        params: { path: { item_id: itemId } },
      });
      if (error) throw new Error('promote failed');
      await reselect();
    },
    [reselect],
  );

  useEffect(() => {
    void refresh();
    void refreshProjects();
    // Intentionally run once on mount; the actions are stable for the initial load.
  }, []);

  const value = useMemo<FlowState>(
    () => ({
      items,
      selected,
      selectedId,
      loadingList,
      refresh,
      select,
      capture,
      expand,
      process,
      getPlan,
      getClarify,
      submitClarify,
      getPreview,
      projects,
      refreshProjects,
      approve,
      reject,
      promote,
    }),
    [
      items,
      selected,
      selectedId,
      loadingList,
      refresh,
      select,
      capture,
      expand,
      process,
      getPlan,
      getClarify,
      submitClarify,
      getPreview,
      projects,
      refreshProjects,
      approve,
      reject,
      promote,
    ],
  );

  return <FlowContext.Provider value={value}>{children}</FlowContext.Provider>;
}

export function useFlow(): FlowState {
  const context = useContext(FlowContext);
  if (context === null) throw new Error('useFlow must be used within FlowProvider');
  return context;
}
