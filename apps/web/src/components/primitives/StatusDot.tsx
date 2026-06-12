export type DotState =
  | 'done'
  | 'current'
  | 'gate'
  | 'pending'
  | 'live'
  | 'warn'
  | 'error';

const STYLES: Record<DotState, { color: string; glow: boolean }> = {
  done: { color: 'var(--status-green)', glow: false },
  current: { color: 'var(--accent)', glow: true },
  gate: { color: 'var(--gate-gold)', glow: false },
  pending: { color: 'var(--faint)', glow: false },
  live: { color: 'var(--status-green)', glow: true },
  warn: { color: 'var(--gate-gold)', glow: true },
  error: { color: 'var(--danger)', glow: true },
};

// The small status dot. green done, orange current, gold gate, grey pending, green-glow
// live, gold-glow warn, danger-glow error.
export function StatusDot({ state, label }: { state: DotState; label?: string }) {
  const style = STYLES[state];
  return (
    <span
      role={label ? 'img' : undefined}
      aria-label={label ?? `${state} status`}
      className="inline-block h-2 w-2 shrink-0 rounded-full"
      style={{
        backgroundColor: style.color,
        boxShadow: style.glow ? `0 0 8px ${style.color}` : undefined,
      }}
    />
  );
}
