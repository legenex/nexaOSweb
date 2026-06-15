import type { ReactNode } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { MonoLabel, Pill } from '../../components/primitives';
import { ConfidenceMeter } from './parts';

type DashboardSummary = Schemas['DashboardSummary'];

// A compact pipeline tile. Tighter than the old radar card so several read in one glance; the
// count rides next to the label rather than as a large figure, since the headline numbers now
// live in the pulse bar above.
function Tile({ label, count, children }: { label: string; count: number; children: ReactNode }) {
  return (
    <div className="rounded-glass border border-line bg-surface/60 p-4">
      <div className="mb-2 flex items-center justify-between">
        <MonoLabel tone="accent">{label}</MonoLabel>
        <span className="mono-meta text-faint">{count}</span>
      </div>
      {children}
    </div>
  );
}

// The pipeline: the live lists behind the pulse bar counts (projects in build, builds at the
// gate, findings to convert, open tasks, recent captures). Health, connectors, and model usage
// moved to the pulse bar and the AI systems rail, so this stays focused on work in flight. Only
// tiles with content render; when the whole pipeline is clear, a single calm line shows instead.
export function CommandRadar({ summary }: { summary: DashboardSummary }) {
  const hasAny =
    summary.active_projects.length > 0 ||
    summary.builds_awaiting_approval.length > 0 ||
    summary.research_ready.length > 0 ||
    summary.suggested_tasks.length > 0 ||
    summary.recent_uploads.length > 0;

  if (!hasAny) {
    return (
      <div className="rounded-glass border border-line bg-surface/40 px-4 py-3">
        <p className="text-sm text-muted">
          Pipeline clear. Capture an idea or pull from research to put work in flight.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {summary.active_projects.length > 0 ? (
        <Tile label="active projects" count={summary.active_projects_count}>
          <ul className="space-y-1.5">
            {summary.active_projects.map((project) => (
              <li key={project.id} className="flex items-center justify-between gap-2">
                <span className="truncate text-sm text-cream">{project.name}</span>
                <Pill variant="green">{project.stage}</Pill>
              </li>
            ))}
          </ul>
        </Tile>
      ) : null}

      {summary.builds_awaiting_approval.length > 0 ? (
        <Tile label="awaiting approval" count={summary.builds_awaiting_approval_count}>
          <ul className="space-y-1.5">
            {summary.builds_awaiting_approval.map((project) => (
              <li key={project.id} className="flex items-center justify-between gap-2">
                <span className="truncate text-sm text-cream">{project.name}</span>
                <Pill variant="accent">gate</Pill>
              </li>
            ))}
          </ul>
        </Tile>
      ) : null}

      {summary.research_ready.length > 0 ? (
        <Tile label="research ready" count={summary.research_ready_count}>
          <ul className="space-y-1.5">
            {summary.research_ready.map((finding) => (
              <li key={finding.id} className="flex items-center justify-between gap-2">
                <span className="truncate text-sm text-cream">{finding.name}</span>
                <ConfidenceMeter value={finding.confidence} />
              </li>
            ))}
          </ul>
        </Tile>
      ) : null}

      {summary.suggested_tasks.length > 0 ? (
        <Tile label="suggested tasks" count={summary.suggested_tasks_count}>
          <ul className="space-y-1.5">
            {summary.suggested_tasks.map((task) => (
              <li key={task.id} className="truncate text-sm text-cream">
                {task.title}
              </li>
            ))}
          </ul>
        </Tile>
      ) : null}

      {summary.recent_uploads.length > 0 ? (
        <Tile label="recent uploads" count={summary.recent_uploads.length}>
          <ul className="space-y-1.5">
            {summary.recent_uploads.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-2">
                <span className="truncate text-sm text-cream">{item.name}</span>
                <Pill variant="grey">{item.source}</Pill>
              </li>
            ))}
          </ul>
        </Tile>
      ) : null}
    </div>
  );
}
