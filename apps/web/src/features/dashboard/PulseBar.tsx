import type { Schemas } from '@nexaosweb/api-client';

import { StatusDot } from '../../components/primitives';

type DashboardSummary = Schemas['DashboardSummary'];

// One compact metric. A non zero count lifts to accent so the eye lands on what is live; an
// empty count stays calm in cream. Colour comes from brand classes only.
function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-baseline gap-1.5 rounded-lg border border-line bg-surface/60 px-3 py-1.5">
      <span
        className={`font-mono text-lg font-semibold leading-none ${
          value > 0 ? 'text-accent' : 'text-cream'
        }`}
      >
        {value}
      </span>
      <span className="mono-label text-faint">{label}</span>
    </div>
  );
}

// The pulse bar. The headline state, condensed to a single row and pinned to the top of the
// dashboard scroll so it stays in view while the cockpit below scrolls. It replaces the old
// full height tile grid: the numbers live here, the lists live in the pipeline lower down.
export function PulseBar({ summary }: { summary: DashboardSummary }) {
  const { brain } = summary;
  return (
    <div className="sticky top-0 z-20 rounded-glass border border-line bg-canvas/80 px-3 py-2 backdrop-blur-md">
      <div className="flex flex-wrap items-center gap-2">
        <Metric label="projects" value={summary.active_projects_count} />
        <Metric label="approvals" value={summary.builds_awaiting_approval_count} />
        <Metric label="research" value={summary.research_ready_count} />
        <Metric label="tasks" value={summary.suggested_tasks_count} />
        <Metric label="uploads" value={summary.recent_uploads.length} />

        <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1.5 pl-2">
          <span className="flex items-center gap-1.5">
            <StatusDot state={brain.status === 'ok' ? 'live' : 'error'} />
            <span className="mono-meta text-muted">brain</span>
          </span>
          <span className="flex items-center gap-1.5">
            <StatusDot state={brain.database_connected ? 'live' : 'error'} />
            <span className="mono-meta text-muted">db</span>
          </span>
          <span className="mono-meta text-faint">v{brain.version}</span>
          <span className="mono-meta text-faint">
            dreaming {brain.dreaming_enabled ? 'on' : 'off'} · sweep{' '}
            {brain.sweep_enabled ? 'on' : 'off'}
          </span>
        </div>
      </div>
    </div>
  );
}
