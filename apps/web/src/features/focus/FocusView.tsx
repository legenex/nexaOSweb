import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { settingsRoute } from '../../app/nav';
import { useNavigation } from '../../app/navigation';
import { GlassCard, MonoLabel, Pill, StatusDot } from '../../components/primitives';
import type { DotState } from '../../components/primitives';

type OperatorView = Schemas['OperatorView'];
type RankedActions = Schemas['RankedActions'];
type RankedAction = Schemas['RankedAction'];
type FocusItem = Schemas['FocusItem'];
type SourceRef = Schemas['SourceRef'];

// Risk maps to the shared status dots, so the colour comes from the brand variables, never a
// hardcoded hex: high is the danger edge, medium the gate gold, low the green done signal.
const RISK_DOT: Record<string, DotState> = { high: 'error', medium: 'gate', low: 'done' };

// Every focus item carries a SourceRef. The decide layer has no surface of its own to act in, so
// each item links to where the work actually lives: tasks to Tasks, the Dreaming queue to its
// review in Settings, and projects and runs to Projects.
function navKeyFor(source: SourceRef): string {
  switch (source.type) {
    case 'task':
      return 'tasks';
    case 'dreaming':
      return settingsRoute('knowledge');
    case 'run':
    case 'project':
    default:
      return 'projects';
  }
}

function sourceLabel(source: SourceRef): string {
  switch (source.type) {
    case 'task':
      return 'Open in Tasks';
    case 'dreaming':
      return 'Open Dreaming review';
    default:
      return 'Open in Projects';
  }
}

function ageLabel(days: number): string {
  if (days <= 0) return 'new today';
  return `${days}d old`;
}

function SourceLink({ source }: { source: SourceRef }) {
  const navigate = useNavigation();
  return (
    <button
      type="button"
      onClick={() => navigate(navKeyFor(source))}
      className="mono-label text-accent hover:underline"
    >
      {sourceLabel(source)} →
    </button>
  );
}

// --- operator buckets -----------------------------------------------------------------------

function ItemRow({ item }: { item: FocusItem }) {
  return (
    <li className="flex items-start justify-between gap-3 border-b border-line py-2 last:border-0">
      <div className="min-w-0">
        <p className="text-sm text-cream">{item.title}</p>
        {item.detail ? <p className="mono-meta mt-0.5 text-faint">{item.detail}</p> : null}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <span className="mono-meta text-faint">{ageLabel(item.age_days)}</span>
        <SourceLink source={item.source} />
      </div>
    </li>
  );
}

function Bucket({ label, items, empty }: { label: string; items: FocusItem[]; empty: string }) {
  return (
    <GlassCard className="border-electric">
      <div className="flex items-center justify-between">
        <MonoLabel tone="accent">{label}</MonoLabel>
        <span className="mono-meta text-faint">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{empty}</p>
      ) : (
        <ul className="mt-2">
          {items.map((item, index) => (
            <ItemRow key={`${item.kind}-${item.source.id ?? 'none'}-${index}`} item={item} />
          ))}
        </ul>
      )}
    </GlassCard>
  );
}

// --- ranked actions -------------------------------------------------------------------------

function RankedRow({ action }: { action: RankedAction }) {
  const { factors } = action;
  return (
    <GlassCard className="border-electric">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mono-label shrink-0 text-accent">#{action.rank}</span>
          <div className="min-w-0">
            <p className="text-sm text-cream">{action.title}</p>
            <p className="mt-1 text-xs text-muted">{action.reason}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1">
                <StatusDot state={RISK_DOT[factors.risk] ?? 'pending'} label={`${factors.risk} risk`} />
                <span className="mono-meta text-faint">{factors.risk} risk</span>
              </span>
              <span className="mono-meta text-faint">{ageLabel(factors.age_days)}</span>
              {factors.blocked ? <Pill variant="accent">blocked</Pill> : null}
              {factors.autonomy_eligible ? <Pill variant="green">delegable</Pill> : null}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="mono-meta text-faint">score {action.score}</span>
          <SourceLink source={action.source} />
        </div>
      </div>
    </GlassCard>
  );
}

// --- view -----------------------------------------------------------------------------------

export function FocusView() {
  const [operator, setOperator] = useState<OperatorView | null>(null);
  const [ranked, setRanked] = useState<RankedActions | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    const [op, rk] = await Promise.all([api.GET('/focus/operator'), api.GET('/focus/ranked')]);
    if (op.error || !op.data || rk.error || !rk.data) {
      setError(true);
      return;
    }
    setError(false);
    setOperator(op.data as OperatorView);
    setRanked(rk.data as RankedActions);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return <p className="text-sm text-muted">Focus is unavailable. Check the Brain connection.</p>;
  }
  if (!operator || !ranked) {
    return <p className="text-sm text-muted">Ranking your work…</p>;
  }

  // Honest empty state: when nothing ranks, say so plainly rather than showing empty scaffolding.
  if (ranked.actions.length === 0) {
    return (
      <GlassCard className="border-electric">
        <MonoLabel tone="faint">all clear</MonoLabel>
        <p className="mt-2 text-sm text-muted">
          Nothing needs your attention right now. Approvals waiting, blocked work, projects that
          stall past {operator.stale_threshold_days} days, and tasks ready to close out will surface
          here as they arrive, each ranked with the reason it matters.
        </p>
      </GlassCard>
    );
  }

  const recommended = operator.recommended_next_actions;

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <div className="flex items-center gap-2 border-b border-line pb-2">
          <MonoLabel tone="accent">recommended next actions</MonoLabel>
          <span className="mono-meta text-faint">top {recommended.length}</span>
        </div>
        <div className="space-y-3">
          {recommended.map((action) => (
            <RankedRow key={`rec-${action.rank}`} action={action} />
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="border-b border-line pb-2">
          <MonoLabel tone="faint">operator view</MonoLabel>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <Bucket
            label="approvals waiting"
            items={operator.approvals_waiting}
            empty="No approvals waiting."
          />
          <Bucket
            label="blocked work"
            items={operator.blocked_work}
            empty="Nothing is blocked."
          />
          <Bucket
            label="stale projects"
            items={operator.stale_projects}
            empty={`No project has stalled past ${operator.stale_threshold_days} days.`}
          />
          <Bucket
            label="tasks safe to complete"
            items={operator.tasks_safe_to_complete}
            empty="No quick tasks to close out."
          />
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center gap-2 border-b border-line pb-2">
          <MonoLabel tone="faint">all ranked actions</MonoLabel>
          <span className="mono-meta text-faint">{ranked.actions.length}</span>
        </div>
        <div className="space-y-3">
          {ranked.actions.map((action) => (
            <RankedRow key={`all-${action.rank}`} action={action} />
          ))}
        </div>
      </section>
    </div>
  );
}
