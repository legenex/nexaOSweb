import { useEffect, useRef, useState } from 'react';

import { apiFetch } from '../app/api';
import { useNavigation } from '../app/navigation';
import { useReducedMotion } from '../app/useReducedMotion';
import { useFlow } from '../features/flow/FlowProvider';
import { HoloObject } from './HoloObject';
import { DocumentIcon, ImageIcon, JournalIcon, VoiceIcon } from './paletteIcons';
import { MonoLabel } from './primitives';

// Ask Nexa, redesigned as a Spotlight style command palette. Collapsed it is a compact control
// in the sidebar. On click or focus it opens a centered floating overlay, holographic, with the
// electric border treatment, a quick scale and fade that reduced motion disables, and the rest
// of the app dimmed behind it. It keeps the original behaviour (Ask runs the Brain expand pass,
// Capture posts to /intake/capture, a capture can route to Project Builder) and adds an action
// row of four upload affordances. Mounted once in the shell sidebar, reachable everywhere.

type Result =
  | { kind: 'answer'; text: string }
  | { kind: 'captured'; name: string; id: number }
  | { kind: 'error'; text: string };

type Busy = 'ask' | 'capture' | 'document' | 'image' | 'voice' | 'journal' | null;

export function CommandBar() {
  const { capture, expand } = useFlow();
  const navigate = useNavigation();
  const reduced = useReducedMotion();

  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState<Busy>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [recording, setRecording] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const docInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const audioInputRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);

  const close = () => {
    setOpen(false);
    setResult(null);
  };

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Close on Escape from anywhere while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
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

  // Document and Image: post the chosen file to /intake/capture as the file field, tagging the
  // source so the pipeline knows what arrived.
  const uploadFile = async (file: File, source: 'document' | 'image') => {
    setBusy(source);
    setResult(null);
    try {
      const item = await capture({ name: file.name, body: '', source, file });
      setResult({ kind: 'captured', name: item.name, id: item.id });
    } catch {
      setResult({ kind: 'error', text: `Could not upload that ${source}.` });
    } finally {
      setBusy(null);
    }
  };

  // Voice note: send recorded or picked audio to /journal/transcribe, then place the transcript
  // in the input for Ask or Capture. The transcribe endpoint is the canonical target; its Brain
  // implementation lands in a later milestone, so a missing endpoint surfaces as a clear error.
  const transcribe = async (audio: Blob, filename: string) => {
    setBusy('voice');
    setResult(null);
    try {
      const form = new FormData();
      form.append('file', audio, filename);
      const response = await apiFetch('/journal/transcribe', { method: 'POST', body: form });
      if (!response.ok) throw new Error('transcribe failed');
      const data = (await response.json()) as { transcript?: string; text?: string };
      const transcript = (data.transcript ?? data.text ?? '').trim();
      if (transcript) {
        setText(transcript);
        inputRef.current?.focus();
      } else {
        setResult({ kind: 'error', text: 'No speech was transcribed.' });
      }
    } catch {
      setResult({ kind: 'error', text: 'Voice transcription is not available yet.' });
    } finally {
      setBusy(null);
    }
  };

  const toggleRecording = async () => {
    if (busy && busy !== 'voice') return;
    if (recording) {
      recorderRef.current?.stop();
      return;
    }
    // Try to record from the mic; fall back to picking an audio file if that is unavailable.
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      audioInputRef.current?.click();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => chunks.push(event.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        setRecording(false);
        recorderRef.current = null;
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
        void transcribe(blob, 'voice-note.webm');
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      // Permission denied or unsupported: fall back to the file picker.
      audioInputRef.current?.click();
    }
  };

  // Journal: no dedicated journal entry endpoint exists yet, so capture the current input as an
  // item with source journal as the interim path.
  // TODO: route to a real Journal surface and endpoint once Journal ships its own feature.
  const doJournal = async () => {
    const body = text.trim();
    if (!body || busy) return;
    setBusy('journal');
    setResult(null);
    try {
      const item = await capture({ name: body.slice(0, 80), body, source: 'journal' });
      setResult({ kind: 'captured', name: item.name, id: item.id });
      setText('');
    } catch {
      setResult({ kind: 'error', text: 'Could not save that journal note.' });
    } finally {
      setBusy(null);
    }
  };

  const actions: Array<{
    key: string;
    label: string;
    icon: JSX.Element;
    onClick: () => void;
    active?: boolean;
    disabled?: boolean;
  }> = [
    {
      key: 'document',
      label: 'Upload a document',
      icon: <DocumentIcon />,
      onClick: () => docInputRef.current?.click(),
    },
    {
      key: 'image',
      label: 'Upload an image',
      icon: <ImageIcon />,
      onClick: () => imageInputRef.current?.click(),
    },
    {
      key: 'voice',
      label: recording ? 'Stop recording' : 'Record a voice note',
      icon: <VoiceIcon />,
      onClick: () => void toggleRecording(),
      active: recording,
    },
    {
      key: 'journal',
      label: 'Save as a journal note',
      icon: <JournalIcon />,
      onClick: () => void doJournal(),
      disabled: !text.trim(),
    },
  ];

  return (
    <>
      {/* Collapsed: a compact control in the sidebar. The placeholder label sits on the mid
          tone muted variable, not the near invisible faint one, so it stays legible. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        onFocus={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="Ask Nexa"
        className="flex w-full items-center gap-2 rounded-md border border-line bg-surface/40 px-3 py-2 text-left transition hover:border-accent"
      >
        <span aria-hidden className="text-accent">
          ⌕
        </span>
        <MonoLabel tone="muted">ask nexa</MonoLabel>
      </button>

      {/* Hidden file inputs backing the upload affordances. */}
      <input
        ref={docInputRef}
        type="file"
        accept=".pdf,.md,.markdown,.txt,.doc,.docx,.rtf,.csv"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void uploadFile(file, 'document');
          event.target.value = '';
        }}
      />
      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void uploadFile(file, 'image');
          event.target.value = '';
        }}
      />
      <input
        ref={audioInputRef}
        type="file"
        accept="audio/*"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void transcribe(file, file.name);
          event.target.value = '';
        }}
      />

      {/* Open: a centered Spotlight overlay. The backdrop dims and closes the app behind it. */}
      {open ? (
        <div
          className={`fixed inset-0 z-50 flex items-start justify-center bg-black/60 px-4 pt-[18vh] ${
            reduced ? '' : 'palette-dim'
          }`}
          onMouseDown={close}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Ask Nexa"
            onMouseDown={(event) => event.stopPropagation()}
            className={`border-electric relative w-full max-w-xl overflow-hidden rounded-glass border border-line bg-surface/95 p-4 shadow-[0_24px_80px_rgba(0,0,0,0.55)] backdrop-blur-md ${
              reduced ? '' : 'palette-pop'
            }`}
          >
            {/* Holographic accent, kept faint behind the content. */}
            <HoloObject
              variant="insights"
              size={96}
              className="pointer-events-none absolute -right-2 -top-2 z-0 opacity-40"
            />

            <div className="relative z-10">
              <div className="flex items-center gap-2">
                <span aria-hidden className="text-lg text-accent">
                  ⌕
                </span>
                <input
                  ref={inputRef}
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void ask();
                  }}
                  placeholder="Ask Nexa, or capture an idea"
                  spellCheck={false}
                  aria-label="Ask Nexa input"
                  className="min-w-0 flex-1 bg-transparent py-1.5 text-base text-cream outline-none placeholder:text-muted"
                />

                {/* Action row: four upload affordances on the right of the input. */}
                <div className="flex shrink-0 items-center gap-1">
                  {actions.map((action) => (
                    <button
                      key={action.key}
                      type="button"
                      onClick={action.onClick}
                      disabled={action.disabled || (busy !== null && !action.active)}
                      aria-label={action.label}
                      aria-pressed={action.active}
                      title={action.label}
                      className={[
                        'rounded-md border p-2 transition disabled:opacity-40',
                        action.active
                          ? 'border-accent bg-accent/15 text-accent'
                          : 'border-line text-muted hover:border-accent hover:text-accent',
                      ].join(' ')}
                    >
                      {action.icon}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-3 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void ask()}
                  disabled={!text.trim() || busy !== null}
                  className="mono-label flex-1 rounded-md border border-accent px-3 py-1.5 text-accent hover:bg-accent/10 disabled:opacity-50"
                >
                  {busy === 'ask' ? 'asking' : 'ask'}
                </button>
                <button
                  type="button"
                  onClick={() => void doCapture()}
                  disabled={!text.trim() || busy !== null}
                  className="mono-label flex-1 rounded-md bg-accent px-3 py-1.5 text-black hover:bg-accent-hi disabled:opacity-50"
                >
                  {busy === 'capture' ? 'capturing' : 'capture'}
                </button>
              </div>

              {recording ? (
                <p className="mt-2 flex items-center gap-2 text-sm text-muted">
                  <span
                    aria-hidden
                    className="inline-block h-2 w-2 rounded-full bg-danger"
                    style={{ boxShadow: '0 0 8px var(--danger)' }}
                  />
                  Recording. Tap the voice icon again to stop and transcribe.
                </p>
              ) : null}
              {busy === 'voice' && !recording ? (
                <p className="mt-2 text-sm text-muted">Transcribing voice note.</p>
              ) : null}

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
                    <p className="max-h-56 overflow-auto whitespace-pre-wrap text-sm text-cream">
                      {result.text}
                    </p>
                  ) : result.kind === 'captured' ? (
                    <p className="text-sm text-cream">
                      Captured <span className="text-accent">{result.name}</span> into the pipeline.{' '}
                      <button
                        type="button"
                        onClick={() => {
                          navigate('project-builder');
                          close();
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
          </div>
        </div>
      ) : null}
    </>
  );
}
