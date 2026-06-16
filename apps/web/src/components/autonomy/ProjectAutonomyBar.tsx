import { AutonomySelector } from './AutonomySelector';
import { KillSwitch } from './KillSwitch';
import { normalizeLevel } from './levels';
import { useProjectAutonomy } from './useProjectAutonomy';

// The project level autonomy controls bundled together: the kill switch stop control and the green,
// yellow, red default dial that new tasks inherit. Reused on the Projects card and in the Project
// Builder header so both surfaces read and write the same project autonomy state.
export function ProjectAutonomyBar({
  projectId,
  variant = 'card',
}: {
  projectId: number;
  variant?: 'card' | 'header';
}) {
  const { state, loading, busy, error, setDefault, setKill } = useProjectAutonomy(projectId);
  const engaged = state?.kill_switch_engaged ?? false;
  const level = normalizeLevel(state?.default_level);

  const wrap =
    variant === 'header'
      ? 'flex flex-wrap items-center gap-x-6 gap-y-3'
      : 'mt-3 space-y-3 border-t border-line pt-3';

  return (
    <div className={wrap} onClick={(event) => event.stopPropagation()}>
      <KillSwitch
        engaged={engaged}
        busy={busy}
        disabled={loading}
        haltedCount={state?.halted_run_ids.length}
        onToggle={(next) => void setKill(next)}
        size={variant === 'header' ? 'md' : 'sm'}
      />
      <AutonomySelector
        label="Project default"
        value={level}
        onChange={(next) => void setDefault(next)}
        disabled={loading}
        busy={busy}
        size="sm"
      />
      {error ? <p className="mono-meta text-danger">{error}</p> : null}
    </div>
  );
}
