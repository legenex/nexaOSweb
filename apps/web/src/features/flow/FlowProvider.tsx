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
}

const FlowContext = createContext<FlowState | null>(null);

export function FlowProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<FlowItem[]>([]);
  const [selected, setSelected] = useState<FlowItem | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loadingList, setLoadingList] = useState(false);

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

  useEffect(() => {
    void refresh();
    // run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo<FlowState>(
    () => ({ items, selected, selectedId, loadingList, refresh, select, capture, expand }),
    [items, selected, selectedId, loadingList, refresh, select, capture, expand],
  );

  return <FlowContext.Provider value={value}>{children}</FlowContext.Provider>;
}

export function useFlow(): FlowState {
  const context = useContext(FlowContext);
  if (context === null) throw new Error('useFlow must be used within FlowProvider');
  return context;
}
