import type { ReactNode } from 'react';

type Tone = 'muted' | 'accent' | 'cream' | 'faint';

const TONE: Record<Tone, string> = {
  muted: 'text-muted',
  accent: 'text-accent',
  cream: 'text-cream',
  faint: 'text-faint',
};

// The signature mono uppercase label. Used for stage badges, meta, paths, model names.
export function MonoLabel({
  children,
  tone = 'muted',
  className = '',
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return <span className={`mono-label ${TONE[tone]} ${className}`}>{children}</span>;
}
