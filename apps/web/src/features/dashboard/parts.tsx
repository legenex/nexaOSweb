// Small shared pieces for the cockpit. Orange is the only brand colour; the neutral track is
// a white opacity tint, matching the existing chrome rather than a hardcoded hex.

export function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="flex items-center gap-2" title={`confidence ${pct}%`}>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-[0.62rem] text-muted">{pct}%</span>
    </div>
  );
}
