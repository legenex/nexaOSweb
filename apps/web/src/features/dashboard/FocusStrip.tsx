import type { Schemas } from '@nexaosweb/api-client';

import { GlassCard, MonoLabel, Pill } from '../../components/primitives';

type DashboardSummary = Schemas['DashboardSummary'];

interface FocusItem {
  key: string;
  title: string;
  reason: string;
  value: string;
}

// A simple top three derived from real summary state. Read only: the full ranking arrives
// with Focus and Accountability later, so nothing here is invented, it only reflects the
// Brain's aggregate.
function deriveFocus(summary: DashboardSummary): FocusItem[] {
  const items: FocusItem[] = [];

  if (summary.top_opportunity) {
    items.push({
      key: 'opportunity',
      title: summary.top_opportunity.title,
      reason: summary.top_opportunity.detail,
      value: 'opportunity',
    });
  }
  const gate = summary.builds_awaiting_approval[0];
  if (gate && !items.some((item) => item.title.includes(gate.name))) {
    items.push({
      key: `gate-${gate.id}`,
      title: gate.name,
      reason: 'At the human gate, waiting on your approval to build.',
      value: 'approval',
    });
  }
  const finding = summary.research_ready[0];
  if (finding && !items.some((item) => item.title.includes(finding.name))) {
    items.push({
      key: `finding-${finding.id}`,
      title: finding.name,
      reason: 'A research finding ready to convert into a project.',
      value: 'research',
    });
  }
  const task = summary.suggested_tasks[0];
  if (task) {
    items.push({
      key: `task-${task.id}`,
      title: task.title,
      reason: 'An open task in your queue.',
      value: 'task',
    });
  }
  const active = summary.active_projects[0];
  if (active && !items.some((item) => item.title.includes(active.name))) {
    items.push({
      key: `active-${active.id}`,
      title: active.name,
      reason: 'An active build to push one step forward.',
      value: 'build',
    });
  }

  return items.slice(0, 3);
}

export function FocusStrip({ summary }: { summary: DashboardSummary }) {
  const items = deriveFocus(summary);

  return (
    <GlassCard className="border-electric">
      <div className="mb-3 flex items-center justify-between">
        <MonoLabel tone="accent">ai insights</MonoLabel>
        <span className="mono-meta">what to act on now · read only</span>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-muted">
          Nothing to rank yet. As projects, findings, and tasks land, your focus shows here.
        </p>
      ) : (
        <ol className="grid gap-3 md:grid-cols-3">
          {items.map((item, index) => (
            <li key={item.key} className="rounded-md border border-line bg-canvas/40 p-3">
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="font-mono text-xs text-faint">{String(index + 1).padStart(2, '0')}</span>
                <Pill variant="accent">{item.value}</Pill>
              </div>
              <div className="text-sm font-semibold text-cream">{item.title}</div>
              <p className="mt-1 text-xs text-muted">{item.reason}</p>
            </li>
          ))}
        </ol>
      )}
    </GlassCard>
  );
}
