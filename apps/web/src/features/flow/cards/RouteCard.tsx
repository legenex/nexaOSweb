import { GlassCard, MonoLabel, StatusDot } from '../../../components/primitives';
import { useFlow } from '../FlowProvider';

// The eight workflows. The winning route is lit. Non project routes terminate here and the
// later stages dim (reflected by the stage dots in the panorama).
const WORKFLOWS: { route: string; label: string; terminal: boolean }[] = [
  { route: 'project', label: 'Project', terminal: false },
  { route: 'tasks', label: 'Tasks', terminal: true },
  { route: 'journal', label: 'Journal', terminal: true },
  { route: 'campaign', label: 'Campaign', terminal: true },
  { route: 'technical', label: 'Technical', terminal: true },
  { route: 'content', label: 'Content', terminal: true },
  { route: 'park', label: 'Park', terminal: true },
  { route: 'archive', label: 'Archive', terminal: true },
];

export function RouteCard() {
  const { selected } = useFlow();
  const winning = selected?.route ?? null;
  const winningRow = WORKFLOWS.find((entry) => entry.route === winning);

  return (
    <GlassCard>
      <div className="mb-3 flex items-center justify-between">
        <MonoLabel tone="accent">route</MonoLabel>
        {winning ? <MonoLabel tone="faint">{winning}</MonoLabel> : null}
      </div>

      <ul className="space-y-1.5">
        {WORKFLOWS.map((entry) => {
          const isWinner = entry.route === winning;
          return (
            <li key={entry.route} className="flex items-center gap-2">
              <StatusDot state={isWinner ? 'current' : 'pending'} />
              <span className={isWinner ? 'text-sm text-accent' : 'text-sm text-muted'}>
                {entry.label}
              </span>
            </li>
          );
        })}
      </ul>

      {winningRow?.terminal ? (
        <p className="mt-3 text-xs text-faint">
          This is a terminal workflow. The later build stages do not apply.
        </p>
      ) : null}
    </GlassCard>
  );
}
