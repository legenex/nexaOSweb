import { useEffect, useRef, useState } from 'react';

import { useAuth } from '../app/AuthProvider';
import { settingsRoute } from '../app/nav';
import { MonoLabel } from './primitives';

// The signed in identity at the bottom of the sidebar, with a popover menu holding Profile
// settings (routes to Settings, General) and Sign out. Sign out lives here now, moved off the
// top right page header.
export function ProfileFooter({ onNavigate }: { onNavigate: (key: string) => void }) {
  const { me, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const display = me?.name?.trim() || me?.email || 'Signed in';
  const initial = (me?.name?.trim() || me?.email || '?').charAt(0).toUpperCase();

  return (
    <div ref={ref} className="relative mt-auto">
      {open ? (
        <div className="absolute bottom-full left-0 right-0 mb-2 overflow-hidden rounded-md border border-line bg-surface shadow-xl">
          <button
            type="button"
            onClick={() => {
              onNavigate(settingsRoute('general'));
              setOpen(false);
            }}
            className="block w-full px-3 py-2 text-left text-sm text-cream/85 hover:bg-white/5"
          >
            Profile settings
          </button>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              void logout();
            }}
            className="block w-full border-t border-line px-3 py-2 text-left text-sm text-cream/85 hover:bg-white/5"
          >
            Sign out
          </button>
        </div>
      ) : null}

      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition hover:bg-white/5"
      >
        <span
          aria-hidden
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent font-mono text-sm font-semibold text-black"
        >
          {initial}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-cream">{display}</span>
          {me?.role ? <MonoLabel tone="faint">{me.role}</MonoLabel> : null}
        </span>
        <span aria-hidden className="text-cream/60">
          ⋯
        </span>
      </button>
    </div>
  );
}
