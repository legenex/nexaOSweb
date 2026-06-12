import type { ReactNode } from 'react';

// The card material: translucent glass, a one pixel warm border, a glow on the active stage.
export function GlassCard({
  children,
  active = false,
  className = '',
}: {
  children: ReactNode;
  active?: boolean;
  className?: string;
}) {
  return (
    <div
      className={[
        'rounded-glass border bg-surface/70 p-5 backdrop-blur-sm transition',
        active
          ? 'border-accent/60 shadow-[0_0_22px_rgba(255,115,32,0.28)]'
          : 'border-line',
        className,
      ].join(' ')}
    >
      {children}
    </div>
  );
}
