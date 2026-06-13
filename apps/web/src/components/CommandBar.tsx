import { useEffect, useRef, useState } from 'react';

import { useNavigation } from '../app/navigation';
import { useFlow } from '../features/flow/FlowProvider';
import { MonoLabel } from './primitives';

// Ask Nexa, relocated into the sidebar. Collapsed it is a compact search style affordance that
// fits the sidebar width. On click or focus it expands into an overlay panel with the input and
// the Ask and Capture actions, without shifting the nav below. Behaviour is unchanged: Ask runs
// the Brain expand pass, Capture posts to /intake/capture, and a capture can route to Project
// Builder. Mounted once in the shell sidebar, so it stays reachable from every surface.

type Result =
  | { kind: 'answer'; text: string }
  | { kind: 'captured'; name: string; id: number }
  | { kind: 'error'; text: string };

export function CommandBar() {
  const { capture, expand } = useFlow();
  const navigate = useNavigation();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState<'ask' | 'capture' | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Collapse when the focus or pointer leaves the control, so it never traps the layout.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  const ask = async () => {
    const query = text.trim();
    if (!query || busy) return;
    setBusy('ask');
    setResult(null);
    try {
      const answer = await expand(query, '');
      setResult({ kind: 'answer', text: answer });
    } catch {
      setResult({ kind: 'error', text: 'Nexa could not answer that right now.' });
    } finally {
      setBusy(null);
    }
  };

  const doCapture = async () => {
    const name = text.trim();
    if (!name || busy) return;
    setBusy('capture');
    setResult(null);
    try {
      const item = await capture({ name, body: '', source: 'command-bar' });
      setResult({ kind: 'captured', name: item.name, id: item.id });
      setText('');
    } catch {
      setResult({ kind: 'error', text: 'Capture failed. Check the Brain connection.' });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div ref={containerRef} className="relative">
      {/* Collapsed: a compact search style affordance fitting the sidebar width. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        onFocus={() => setOpen(true)}
        aria-expanded={open}
        aria-label="Ask Nexa"
        className="flex w-full items-center gap-2 rounded-md border border-line bg-surface/40 px-3 py-2 text-left transition hover:border-accent"
      >
        <span aria-hidden className="text-accent">
          ⌕
        </span>
        <MonoLabel tone="faint">ask nexa</MonoLabel>
      </button>

      {/* Expanded: an overlay so the nav below does not shift. */}
      {open ? (
        <div className="absolute left-0 right-0 top-full z-40 mt-1 rounded-glass border border-line bg-surface p-3 shadow-xl">
          <input
            ref={inputRef}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void ask();
              if (event.key === 'Escape') setOpen(false);
            }}
            placeholder="Ask, or capture an idea…"
            spellCheck={false}
            aria-label="Ask Nexa input"
            className="w-full rounded-md border border-line bg-canvas px-3 py-1.5 text-sm text-cream outline-none focus:border-accent"
          />

          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => void ask()}
              disabled={!text.trim() || busy !== null}
              className="mono-label flex-1 rounded-md border border-accent px-3 py-1.5 text-accent hover:bg-accent/10 disabled:opacity-50"
            >
              {busy === 'ask' ? 'asking…' : 'ask'}
            </button>
            <button
              type="button"
              onClick={() => void doCapture()}
              disabled={!text.trim() || busy !== null}
              className="mono-label flex-1 rounded-md bg-accent px-3 py-1.5 text-black hover:bg-accent-hi disabled:opacity-50"
            >
              {busy === 'capture' ? 'capturing…' : 'capture'}
            </button>
          </div>

          {result ? (
            <div className="mt-3 border-t border-line pt-3">
              <div className="mb-1 flex items-center justify-between">
                <MonoLabel tone="accent">
                  {result.kind === 'answer'
                    ? 'nexa'
                    : result.kind === 'captured'
                      ? 'captured'
                      : 'error'}
                </MonoLabel>
                <button
                  type="button"
                  onClick={() => setResult(null)}
                  aria-label="Dismiss"
                  className="mono-label rounded-md border border-line px-2 py-0.5 hover:text-accent"
                >
                  close
                </button>
              </div>

              {result.kind === 'answer' ? (
                <p className="max-h-48 overflow-auto whitespace-pre-wrap text-sm text-cream">
                  {result.text}
                </p>
              ) : result.kind === 'captured' ? (
                <p className="text-sm text-cream">
                  Captured <span className="text-accent">{result.name}</span> into the pipeline.{' '}
                  <button
                    type="button"
                    onClick={() => {
                      navigate('project-builder');
                      setResult(null);
                      setOpen(false);
                    }}
                    className="text-accent underline-offset-2 hover:underline"
                  >
                    Open in Project Builder
                  </button>
                </p>
              ) : (
                <p className="text-sm text-muted">{result.text}</p>
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
