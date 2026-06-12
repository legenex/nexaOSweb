import type { ReactNode } from 'react';

type Variant = 'accent' | 'green' | 'grey' | 'solid';

const VARIANTS: Record<Variant, string> = {
  accent: 'border border-accent text-accent',
  green: 'border border-status-green text-status-green',
  grey: 'border border-line text-muted',
  solid: 'bg-accent text-black border border-accent',
};

// Mono uppercase tag. accent for brand, green for product, grey for neutral, solid for the
// classify shape.
export function Pill({
  children,
  variant = 'grey',
  className = '',
}: {
  children: ReactNode;
  variant?: Variant;
  className?: string;
}) {
  return (
    <span
      className={[
        'inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[0.62rem] uppercase tracking-[0.1em]',
        VARIANTS[variant],
        className,
      ].join(' ')}
    >
      {children}
    </span>
  );
}
