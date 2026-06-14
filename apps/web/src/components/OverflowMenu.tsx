import { useEffect, useRef, useState } from 'react';

export interface OverflowItem {
  label: string;
  onClick: () => void;
  danger?: boolean;
}

// A reusable overflow (kebab) menu. A small trigger opens a list of actions; it closes on
// selection, outside click, or Escape. Colours come from brand variables only. When disabled,
// or when there are no items, the trigger stays visible but inert so the surface reads honestly
// (the affordance is shown, just unavailable) rather than vanishing.
export function OverflowMenu({
  items,
  label = 'Actions',
  disabled = false,
}: {
  items: OverflowItem[];
  label?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const inert = disabled || items.length === 0;

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={inert}
        onClick={() => setOpen((value) => !value)}
        className="rounded-md border border-line px-2 py-1 leading-none text-muted transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-line disabled:hover:text-muted"
      >
        ⋯
      </button>
      {open && !inert ? (
        <div
          role="menu"
          className="absolute right-0 top-full z-40 mt-1 w-44 overflow-hidden rounded-md border border-line bg-surface shadow-xl"
        >
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                item.onClick();
              }}
              className={[
                'block w-full px-3 py-2 text-left text-sm transition hover:bg-white/5',
                item.danger ? 'text-danger' : 'text-cream',
              ].join(' ')}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
