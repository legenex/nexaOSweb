import { useState } from 'react';

import { useNavigation } from '../app/navigation';
import { useFlow } from '../features/flow/FlowProvider';
import { MonoLabel } from './primitives';

// The app wide Ask Nexa bar, above the sidebar. It captures an idea into the pipeline, asks a
// basic question (answered by the Brain's expand pass), or routes to Project Builder. Deeper
// actions land later; capture and ask are wired now.

type Result =
  | { kind: 'answer'; text: string }
  | { kind: 'captured'; name: string; id: number }
  | { kind: 'error'; text: string };

export function CommandBar() {
  const { capture, expand } = useFlow();
  const navigate = useNavigation();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState<'ask' | 'capture' | null>(null);
  const [result, setResult] = useState<Result | null>(null);

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
    <div className="relative z-20 border-b border-line bg-canvas/80 px-4 py-2 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <MonoLabel tone="accent">ask nexa</MonoLabel>
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') void ask();
          }}
          placeholder="Ask a question, or capture an idea…"
          spellCheck={false}
          aria-label="Ask Nexa"
          className="flex-1 rounded-md border border-line bg-surface/60 px-3 py-1.5 text-sm text-cream outline-none focus:border-accent"
        />
        <button
          type="button"
          onClick={() => void ask()}
          disabled={!text.trim() || busy !== null}
          className="mono-label rounded-md border border-accent px-3 py-1.5 text-accent hover:bg-accent/10 disabled:opacity-50"
        >
          {busy === 'ask' ? 'asking…' : 'ask'}
        </button>
        <button
          type="button"
          onClick={() => void doCapture()}
          disabled={!text.trim() || busy !== null}
          className="mono-label rounded-md bg-accent px-3 py-1.5 text-black hover:bg-accent-hi disabled:opacity-50"
        >
          {busy === 'capture' ? 'capturing…' : 'capture'}
        </button>
      </div>

      {result ? (
        <div className="absolute left-4 right-4 top-full z-30 mt-1 rounded-glass border border-line bg-surface p-4 shadow-[0_12px_30px_rgba(0,0,0,0.45)]">
          <div className="mb-2 flex items-center justify-between">
            <MonoLabel tone="accent">
              {result.kind === 'answer' ? 'nexa' : result.kind === 'captured' ? 'captured' : 'error'}
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
            <p className="max-w-prose whitespace-pre-wrap text-sm text-cream">{result.text}</p>
          ) : result.kind === 'captured' ? (
            <p className="text-sm text-cream">
              Captured <span className="text-accent">{result.name}</span> into the pipeline.{' '}
              <button
                type="button"
                onClick={() => {
                  navigate('project-builder');
                  setResult(null);
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
  );
}
