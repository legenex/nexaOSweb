import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { Button, MonoLabel } from '../../components/primitives';
import { InsightCard } from './InsightCard';
import type { InsightActionKey } from './InsightCard';

type InsightsResponse = Schemas['InsightsResponse'];
type Insight = Schemas['InsightRead'];

function Section({
  title,
  insights,
  empty,
  onAct,
}: {
  title: string;
  insights: Insight[];
  empty: string;
  onAct: (action: InsightActionKey, insight: Insight) => Promise<string>;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <MonoLabel tone="accent">{title}</MonoLabel>
        <span className="mono-meta text-faint">{insights.length}</span>
      </div>
      {insights.length === 0 ? (
        <p className="text-sm text-muted">{empty}</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {insights.map((insight) => (
            <InsightCard key={insight.id} insight={insight} onAct={onAct} />
          ))}
        </div>
      )}
    </section>
  );
}

export function InsightsView() {
  const [data, setData] = useState<InsightsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    const { data: payload, error: err } = await api.GET('/insights');
    if (err || !payload) {
      setError(true);
      return;
    }
    setError(false);
    setData(payload as InsightsResponse);
  }, []);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      await load();
      setLoading(false);
    })();
  }, [load]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await api.POST('/insights/refresh');
      await load();
    } finally {
      setRefreshing(false);
    }
  }, [load]);

  const onAct = useCallback(
    async (action: InsightActionKey, insight: Insight): Promise<string> => {
      const path = {
        save: '/insights/{insight_id}/save-to-knowledge',
        task: '/insights/{insight_id}/create-task',
        project: '/insights/{insight_id}/create-project',
        dismiss: '/insights/{insight_id}/dismiss',
      }[action] as
        | '/insights/{insight_id}/save-to-knowledge'
        | '/insights/{insight_id}/create-task'
        | '/insights/{insight_id}/create-project'
        | '/insights/{insight_id}/dismiss';

      const { error: err } = await api.POST(path, {
        params: { path: { insight_id: insight.id } },
      });
      if (err) throw new Error(`${action} failed`);
      await load();
      return {
        save: 'Saved to Knowledge',
        task: 'Turned into a task',
        project: 'Turned into a project',
        dismiss: 'Dismissed',
      }[action];
    },
    [load],
  );

  const personal = useMemo(() => data?.personal_patterns ?? [], [data]);
  const work = useMemo(() => data?.work_patterns ?? [], [data]);
  const innovation = useMemo(() => data?.innovation ?? [], [data]);
  const generative = useMemo(
    () => (data?.profile_summary ? [data.profile_summary] : []),
    [data],
  );

  // The approval queue is every still open insight, newest first, across the categories.
  const queue = useMemo(() => {
    const all = [...generative, ...personal, ...work, ...innovation];
    return all.filter((insight) => insight.status === 'active');
  }, [generative, personal, work, innovation]);

  const total = personal.length + work.length + innovation.length + generative.length;

  const refreshButton = (
    <Button onClick={() => void refresh()} disabled={refreshing}>
      {refreshing ? 'refreshing' : 'Refresh insights'}
    </Button>
  );

  if (loading) {
    return <p className="text-sm text-muted">Reading the Knowledge base…</p>;
  }

  if (error) {
    return (
      <section className="rounded-glass border border-line bg-surface/60 p-6">
        <MonoLabel tone="faint">insights unavailable</MonoLabel>
        <p className="mt-2 text-sm text-muted">
          The Brain could not return insights. Check the connection, then refresh.
        </p>
        <div className="mt-3">{refreshButton}</div>
      </section>
    );
  }

  if (total === 0) {
    return (
      <section className="rounded-glass border border-line bg-surface/60 p-6">
        <MonoLabel tone="faint">no insights yet</MonoLabel>
        <p className="mt-2 max-w-prose text-sm text-muted">
          Insights are generated from your Knowledge base. Once there is enough captured,
          consolidated, and researched material, patterns and ideas surface here. Refresh to run a
          generation pass now.
        </p>
        <div className="mt-3">{refreshButton}</div>
      </section>
    );
  }

  const meta: string[] = [];
  if (data?.generated_at) meta.push(`generated ${new Date(data.generated_at).toLocaleString()}`);
  if (data?.extraction_model_key) meta.push(`extraction ${data.extraction_model_key}`);
  if (data?.synthesis_model_key) meta.push(`synthesis ${data.synthesis_model_key}`);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between gap-3">
        {meta.length > 0 ? <span className="mono-meta text-faint">{meta.join(' · ')}</span> : <span />}
        {refreshButton}
      </div>

      <Section
        title="approval queue"
        insights={queue}
        empty="Nothing awaiting review. Actioned and dismissed insights leave the queue."
        onAct={onAct}
      />
      <Section
        title="personal intelligence"
        insights={personal}
        empty="No personal patterns yet."
        onAct={onAct}
      />
      <Section
        title="work intelligence"
        insights={work}
        empty="No work patterns yet."
        onAct={onAct}
      />
      <Section
        title="generative knowledge base"
        insights={generative}
        empty="No synthesized profile yet."
        onAct={onAct}
      />
      <Section
        title="innovation feed"
        insights={innovation}
        empty="No innovation ideas yet."
        onAct={onAct}
      />
    </div>
  );
}
