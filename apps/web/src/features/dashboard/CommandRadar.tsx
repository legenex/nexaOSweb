import type { ReactNode } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { GlassCard, MonoLabel, Pill, StatusDot } from '../../components/primitives';
import type { DotState } from '../../components/primitives';
import { ConfidenceMeter, EmptyLine, TileCount } from './parts';

type DashboardSummary = Schemas['DashboardSummary'];

function Tile({
  label,
  count,
  children,
}: {
  label: string;
  count?: number;
  children: ReactNode;
}) {
  return (
    <GlassCard className="border-electric">
      <div className="mb-2 flex items-center justify-between">
        <MonoLabel tone="accent">{label}</MonoLabel>
        {count !== undefined ? <TileCount value={count} /> : null}
      </div>
      {children}
    </GlassCard>
  );
}

function connectorState(status: string): DotState {
  if (status === 'connected') return 'live';
  if (status === 'available') return 'pending';
  if (status === 'error' || status === 'failed') return 'error';
  return 'warn';
}

export function CommandRadar({ summary }: { summary: DashboardSummary }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <Tile label="active projects" count={summary.active_projects_count}>
        {summary.active_projects.length === 0 ? (
          <EmptyLine>Nothing in build yet.</EmptyLine>
        ) : (
          <ul className="space-y-1.5">
            {summary.active_projects.map((project) => (
              <li key={project.id} className="flex items-center justify-between gap-2">
                <span className="truncate text-sm text-cream">{project.name}</span>
                <Pill variant="green">{project.stage}</Pill>
              </li>
            ))}
          </ul>
        )}
      </Tile>

      <Tile label="awaiting approval" count={summary.builds_awaiting_approval_count}>
        {summary.builds_awaiting_approval.length === 0 ? (
          <EmptyLine>No builds at the gate.</EmptyLine>
        ) : (
          <ul className="space-y-1.5">
            {summary.builds_awaiting_approval.map((project) => (
              <li key={project.id} className="flex items-center justify-between gap-2">
                <span className="truncate text-sm text-cream">{project.name}</span>
                <Pill variant="accent">gate</Pill>
              </li>
            ))}
          </ul>
        )}
      </Tile>

      <Tile label="research ready" count={summary.research_ready_count}>
        {summary.research_ready.length === 0 ? (
          <EmptyLine>No findings to convert.</EmptyLine>
        ) : (
          <ul className="space-y-1.5">
            {summary.research_ready.map((finding) => (
              <li key={finding.id} className="flex items-center justify-between gap-2">
                <span className="truncate text-sm text-cream">{finding.name}</span>
                <ConfidenceMeter value={finding.confidence} />
              </li>
            ))}
          </ul>
        )}
      </Tile>

      <Tile label="suggested tasks" count={summary.suggested_tasks_count}>
        {summary.suggested_tasks.length === 0 ? (
          <EmptyLine>No open tasks.</EmptyLine>
        ) : (
          <ul className="space-y-1.5">
            {summary.suggested_tasks.map((task) => (
              <li key={task.id} className="truncate text-sm text-cream">
                {task.title}
              </li>
            ))}
          </ul>
        )}
      </Tile>

      <Tile label="recent uploads">
        {summary.recent_uploads.length === 0 ? (
          <EmptyLine>Nothing captured recently.</EmptyLine>
        ) : (
          <ul className="space-y-1.5">
            {summary.recent_uploads.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-2">
                <span className="truncate text-sm text-cream">{item.name}</span>
                <Pill variant="grey">{item.source}</Pill>
              </li>
            ))}
          </ul>
        )}
      </Tile>

      <Tile label="connectors">
        {summary.connector_health.length === 0 ? (
          <EmptyLine>No connectors configured.</EmptyLine>
        ) : (
          <ul className="space-y-1.5">
            {summary.connector_health.map((connector) => (
              <li key={connector.provider} className="flex items-center gap-2">
                <StatusDot state={connectorState(connector.status)} />
                <span className="text-sm text-cream">{connector.provider}</span>
                <span className="mono-meta ml-auto">{connector.status}</span>
              </li>
            ))}
          </ul>
        )}
      </Tile>

      <Tile label="model usage">
        {summary.model_usage.length === 0 ? (
          <EmptyLine>No model calls recorded.</EmptyLine>
        ) : (
          <ul className="space-y-1.5">
            {summary.model_usage.map((usage) => (
              <li key={usage.model_key} className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs text-cream">{usage.model_key}</span>
                <span className="mono-meta">{usage.count}</span>
              </li>
            ))}
          </ul>
        )}
      </Tile>

      <Tile label="brain status">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <StatusDot state={summary.brain.status === 'ok' ? 'live' : 'error'} />
            <span className="text-sm text-cream">{summary.brain.status}</span>
            <span className="mono-meta ml-auto">v{summary.brain.version}</span>
          </div>
          <div className="flex items-center gap-2">
            <StatusDot state={summary.brain.database_connected ? 'live' : 'error'} />
            <span className="text-sm text-muted">database</span>
          </div>
          <div className="mono-meta">
            dreaming {summary.brain.dreaming_enabled ? 'on' : 'off'} · sweep{' '}
            {summary.brain.sweep_enabled ? 'on' : 'off'}
          </div>
        </div>
      </Tile>
    </div>
  );
}
