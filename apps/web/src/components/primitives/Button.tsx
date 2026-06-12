import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'primary' | 'outline' | 'muted';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-black hover:bg-accent-hi',
  outline: 'border border-accent text-accent hover:bg-accent/10',
  muted: 'bg-white/5 text-muted hover:bg-white/10',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

// Primary solid orange, outline accent with an arrow glyph, muted translucent grey.
export function Button({ variant = 'primary', className = '', children, ...rest }: ButtonProps) {
  return (
    <button
      className={[
        'inline-flex items-center justify-center gap-1 rounded-lg px-4 py-2 text-sm font-semibold transition disabled:opacity-60',
        VARIANTS[variant],
        className,
      ].join(' ')}
      {...rest}
    >
      {children}
    </button>
  );
}
