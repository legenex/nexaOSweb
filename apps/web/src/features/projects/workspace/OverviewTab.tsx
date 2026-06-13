import { useEffect, useState } from 'react';

import { GlassCard, MonoLabel, Pill, StatusDot } from '../../../components/primitives';
import { getOverview } from './api';
import type { Overview } from './api';

// One labelled field on the overview grid. Renders a dash when the value is absent.
function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <MonoLabel tone="faint" className="block">
        {label}
      </MonoLabel>
      <p className="mt-0.5 text-sm text-cream">{value ? value : 'not set'}</p>
    </div>
  );
}

export function OverviewTab({ projectId }: { projectId: number }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOverview(null);
    setError(null);
    getOverview(projectId)
      .then(setOverview)
      .catch((err: Error) => setError(err.message));
  }, [projectId]);

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!overview) return <MonoLabel tone="faint">loading overview</MonoLabel>;

  const integrations = overview.connected_integrations ?? [];
  const updated = overview.last_updated ? new Date(overview.last_updated).toLocaleString() : null;

  return (
    <div className="space-y-4">
      <GlassCard className="border-electric">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <h3 className="text-base font-semibold text-cream">{overview.name}</h3>
          <Pill variant="solid">{overview.type}</Pill>
          <Pill
            variant={overview.stage === 'build' || overview.stage === 'live' ? 'green' : 'accent'}
          >
            {overview.stage}
          </Pill>
          <Pill variant="grey">{overview.status}</Pill>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="build destination" value={overview.build_destination} />
          <Field label="url" value={overview.url} />
          <Field label="repo" value={overview.repo} />
          <Field label="local path" value={overview.local_path} />
          <Field label="priority" value={overview.priority} />
          <Field label="revenue potential" value={overview.revenue_potential} />
          <Field label="last updated" value={updated} />
        </div>
      </GlassCard>

      <div className="grid gap-4 md:grid-cols-2">
        <GlassCard>
          <MonoLabel tone="accent" className="mb-2 block">
            current blocker
          </MonoLabel>
          <p className="text-sm text-cream">
            {overview.current_blocker ? overview.current_blocker : 'No blocker recorded.'}
          </p>
        </GlassCard>
        <GlassCard>
          <MonoLabel tone="accent" className="mb-2 block">
            next recommended action
          </MonoLabel>
          <p className="text-sm text-cream">
            {overview.next_recommended_action
              ? overview.next_recommended_action
              : 'Nothing queued.'}
          </p>
        </GlassCard>
      </div>

      <GlassCard>
        <MonoLabel tone="accent" className="mb-3 block">
          connected integrations
        </MonoLabel>
        {integrations.length === 0 ? (
          <p className="text-sm text-muted">No integrations selected for this project.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {integrations.map((integration) => (
              <li
                key={integration.provider}
                className="inline-flex items-center gap-2 rounded-md border border-line px-2 py-1"
              >
                <StatusDot
                  state={integration.status === 'connected' ? 'live' : 'pending'}
                  label={`${integration.provider} ${integration.status}`}
                />
                <span className="text-sm text-cream">{integration.provider}</span>
                <MonoLabel tone="faint">{integration.status}</MonoLabel>
              </li>
            ))}
          </ul>
        )}
      </GlassCard>
    </div>
  );
}
