import { useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { MonoLabel, Pill, StatusDot } from '../../components/primitives';

type SkillsResponse = Schemas['SkillsResponse'];

// Skills and Connectors, read only. Agent facing skills come from the model config resolved
// through the router; connector health mirrors the user's integrations. There is no write
// surface here yet, so each section shows a clear empty state when nothing is present.
export function SkillsPanel() {
  const [data, setData] = useState<SkillsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .GET('/skills')
      .then(({ data: payload }) => {
        if (payload) setData(payload as SkillsResponse);
        else setError('Could not load skills.');
      })
      .catch(() => setError('Could not load skills.'));
  }, []);

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!data) return <MonoLabel tone="faint">loading skills</MonoLabel>;

  return (
    <div className="max-w-2xl space-y-6">
      <section>
        <MonoLabel tone="accent" className="mb-2 block">
          agent skills
        </MonoLabel>
        {data.skills.length === 0 ? (
          <p className="text-sm text-muted">No agent skills are registered yet.</p>
        ) : (
          <ul className="divide-y divide-line/60 rounded-glass border border-line bg-surface/40">
            {data.skills.map((skill) => (
              <li key={skill.id} className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-cream">{skill.label}</span>
                  <Pill variant="accent">{skill.model_key}</Pill>
                  {skill.resolved_model ? (
                    <MonoLabel tone="faint">{skill.resolved_model}</MonoLabel>
                  ) : null}
                </div>
                {skill.description ? (
                  <p className="mt-1 text-sm text-muted">{skill.description}</p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <MonoLabel tone="accent" className="mb-2 block">
          connector health
        </MonoLabel>
        {data.connectors.length === 0 ? (
          <p className="text-sm text-muted">
            No connectors yet. Connect a provider in Integrations to see its health here.
          </p>
        ) : (
          <ul className="divide-y divide-line/60 rounded-glass border border-line bg-surface/40">
            {data.connectors.map((connector) => (
              <li key={connector.provider} className="flex items-center gap-3 px-4 py-3">
                <StatusDot
                  state={connector.status === 'connected' ? 'live' : 'pending'}
                  label={`${connector.provider} ${connector.status}`}
                />
                <span className="flex-1 text-sm text-cream">{connector.provider}</span>
                <MonoLabel tone="faint">{connector.status}</MonoLabel>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
