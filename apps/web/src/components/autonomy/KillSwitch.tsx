import { MonoLabel, StatusDot } from '../primitives';

// The prominent kill switch stop control. Released, it is a clear danger outline button that stops
// every agent for the project. Engaged, it becomes an unmistakable solid danger block with a clear
// label and a Release action; while engaged the project refuses new runs and the Send to agent
// control is disabled elsewhere with a visible reason. The button is keyboard operable and labelled,
// aria-pressed reflects the engaged state, and all color comes from the danger CSS variable.
export function KillSwitch({
  engaged,
  onToggle,
  busy = false,
  disabled = false,
  haltedCount,
  size = 'md',
}: {
  engaged: boolean;
  onToggle: (next: boolean) => void;
  busy?: boolean;
  disabled?: boolean;
  haltedCount?: number;
  size?: 'sm' | 'md';
}) {
  const locked = busy || disabled;
  const pad = size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-2 text-sm';

  if (engaged) {
    const halted = typeof haltedCount === 'number' && haltedCount > 0;
    return (
      <div className="rounded-lg border border-danger bg-danger/10 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="inline-flex items-center gap-2">
            <StatusDot state="error" label="kill switch engaged" />
            <MonoLabel className="text-danger">agents stopped</MonoLabel>
          </span>
          <button
            type="button"
            aria-pressed={true}
            aria-label="Release the kill switch and allow agents to run again"
            disabled={locked}
            onClick={() => !locked && onToggle(false)}
            className={`inline-flex items-center justify-center gap-1 rounded-lg border border-danger font-semibold text-danger transition hover:bg-danger/15 disabled:opacity-60 ${pad}`}
          >
            {busy ? 'working' : 'Release'}
          </button>
        </div>
        <p className="mt-2 mono-meta text-danger">
          {halted
            ? `Kill switch engaged. ${haltedCount} in flight run${haltedCount === 1 ? '' : 's'} halted; new runs are refused until released.`
            : 'Kill switch engaged. New runs are refused until released.'}
        </p>
      </div>
    );
  }

  return (
    <button
      type="button"
      aria-pressed={false}
      aria-label="Engage the kill switch to stop all agents for this project"
      disabled={locked}
      onClick={() => !locked && onToggle(true)}
      className={`inline-flex items-center justify-center gap-2 rounded-lg border border-danger font-semibold text-danger transition hover:bg-danger/10 disabled:opacity-60 ${pad}`}
    >
      <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-[2px] bg-danger" />
      {busy ? 'working' : 'Stop all agents'}
    </button>
  );
}
