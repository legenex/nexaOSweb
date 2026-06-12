import type { ReactNode } from 'react';

// Small shared building blocks for the Knowledge tabs. Orange is the only brand colour, all
// tones come from CSS variables; the neutral track uses a white opacity tint, matching the
// existing chrome (hover:bg-white/5) rather than a hardcoded hex.

export function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="flex items-center gap-2" title={`confidence ${pct}%`}>
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs text-muted">{pct}%</span>
    </div>
  );
}

export function Provenance({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data ?? {});
  if (entries.length === 0) return null;
  return (
    <div className="mt-2 rounded-md border border-line bg-canvas/40 px-2 py-1.5">
      {entries.map(([key, value]) => (
        <div key={key} className="font-mono text-[0.62rem] leading-relaxed text-faint">
          <span className="text-muted">{key}</span>:{' '}
          {typeof value === 'object' ? JSON.stringify(value) : String(value)}
        </div>
      ))}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
  disabled = false,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line/60 py-3 last:border-b-0">
      <div>
        <div className="text-sm text-cream">{label}</div>
        {hint ? <div className="mt-0.5 text-xs text-muted">{hint}</div> : null}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={[
          'relative h-6 w-11 shrink-0 rounded-full border transition disabled:opacity-50',
          checked ? 'border-accent bg-accent' : 'border-line bg-white/5',
        ].join(' ')}
      >
        <span
          className={[
            'absolute top-0.5 h-4 w-4 rounded-full bg-cream transition-all',
            checked ? 'left-[22px]' : 'left-0.5',
          ].join(' ')}
        />
      </button>
    </div>
  );
}

export function FieldShell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mono-label">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
