import { useEffect } from 'react';
import type { ReactNode } from 'react';

import { MonoLabel } from './MonoLabel';

// A centered glass modal. Closes on backdrop click and Escape.
export function Modal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6"
      onClick={onClose}
    >
      <div
        className="max-h-[80vh] w-full max-w-lg overflow-auto rounded-glass border border-line bg-surface p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <MonoLabel tone="accent">{title}</MonoLabel>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="mono-label rounded-md border border-line px-2 py-1 hover:text-accent"
          >
            close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
