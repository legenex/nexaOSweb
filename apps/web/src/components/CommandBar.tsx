import { useEffect, useRef, useState } from 'react';

import { apiFetch } from '../app/api';
import { api } from '../app/client';
import { useNavigation } from '../app/navigation';
import { useReducedMotion } from '../app/useReducedMotion';
import { useFlow } from '../features/flow/FlowProvider';
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
  | { kind: 'journaled' }
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

  // Voice note: upload the recorded audio to /journal/transcribe, then place the transcript in
  // the input for Ask or Capture. Only a genuine 501 from the Brain reads as "not available
  // yet"; every other failure gets its own distinct message.
  const transcribe = async (audio: Blob, filename: string) => {
    setBusy('voice');
    setResult(null);
    try {
      const form = new FormData();
      form.append('file', audio, filename);
      const response = await apiFetch('/journal/transcribe', { method: 'POST', body: form });
      if (response.status === 501) {
        setResult({ kind: 'error', text: 'Voice transcription is not available yet.' });
        return;
      }
      if (!response.ok) {
        setResult({ kind: 'error', text: 'Could not transcribe the recording. Try again.' });
        return;
      }
      const data = (await response.json()) as { transcript?: string; text?: string };
      const transcript = (data.transcript ?? data.text ?? '').trim();
      if (transcript) {
        setText(transcript);
        inputRef.current?.focus();
      } else {
        setResult({ kind: 'error', text: 'No speech was detected in the recording.' });
      }
    } catch {
      setResult({
        kind: 'error',
        text: 'Could not reach the Brain to transcribe. Check the connection.',
      });
    } finally {
      setBusy(null);
    }
  };

  // Pick a recording mime the browser supports and the Brain (whisper) accepts.
  const pickMime = (): string | undefined => {
    if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return undefined;
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
    return candidates.find((type) => MediaRecorder.isTypeSupported(type));
  };

  const startRecording = async () => {
    // Failure state 2: no secure context or an unsupported browser. getUserMedia is only exposed
    // on secure origins, so report that distinctly rather than as a generic failure.
    const insecure = typeof window !== 'undefined' && window.isSecureContext === false;
    const unsupported =
      typeof navigator === 'undefined' ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === 'undefined';
    if (insecure || unsupported) {
      setResult({
        kind: 'error',
        text: insecure
          ? 'Recording needs a secure context. Open this app over https to use the microphone.'
          : 'This browser does not support in app voice recording.',
      });
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      // Failure state 1: permission denied, told apart from other capture errors.
      const name = error instanceof DOMException ? error.name : '';
      if (name === 'NotAllowedError' || name === 'SecurityError' || name === 'PermissionDeniedError') {
        setResult({
          kind: 'error',
          text: 'Microphone permission denied. Allow mic access in your browser, then try again.',
        });
      } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
        setResult({ kind: 'error', text: 'No microphone was found on this device.' });
      } else {
        setResult({ kind: 'error', text: 'Could not start recording. Try again.' });
      }
      return;
    }

    // Failure state 3: recording errors surface distinctly via onerror and the start guard.
    try {
      const mime = pickMime();
      const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data);
      };
      recorder.onerror = () => {
        stream.getTracks().forEach((track) => track.stop());
        setRecording(false);
        recorderRef.current = null;
        setResult({ kind: 'error', text: 'Recording failed. Try again.' });
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        setRecording(false);
        recorderRef.current = null;
        if (chunks.length === 0) {
          setResult({ kind: 'error', text: 'Nothing was recorded. Try again.' });
          return;
        }
        const type = recorder.mimeType || mime || 'audio/webm';
        const ext = type.includes('ogg') ? 'ogg' : type.includes('mp4') ? 'm4a' : 'webm';
        void transcribe(new Blob(chunks, { type }), `voice-note.${ext}`);
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
      setResult(null);
    } catch {
      stream.getTracks().forEach((track) => track.stop());
      setResult({ kind: 'error', text: 'Could not start recording. Try again.' });
    }
  };

  const toggleRecording = async () => {
    if (busy && busy !== 'voice') return;
    if (recording) {
      recorderRef.current?.stop();
      return;
    }
    await startRecording();
  };

  // Journal: save the current input (often a transcribed voice note) as a real Journal entry.
  // This is the end of the voice path: record, transcribe into the input, then save here.
  const doJournal = async () => {
    const body = text.trim();
    if (!body || busy) return;
    setBusy('journal');
    setResult(null);
    try {
      const { error } = await api.POST('/journal/entries', {
        body: { body, mood: null, tags: [], topic_id: null },
      });
      if (error) throw new Error('journal failed');
      setResult({ kind: 'journaled' });
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
            className={`border-electric border-electric-on relative w-full max-w-xl rounded-glass border border-line bg-surface/95 p-7 shadow-[0_24px_80px_rgba(0,0,0,0.55)] backdrop-blur-md ${
              reduced ? '' : 'palette-pop'
            }`}
          >
            <div>
              <div className="flex items-center gap-4">
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

                {/* Action row: four upload affordances, set off from the input edge as a
                    clearly separated cluster. */}
                <div className="flex shrink-0 items-center gap-2 border-l border-line pl-4">
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

              <div className="mt-6 flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => void ask()}
                  disabled={!text.trim() || busy !== null}
                  className="mono-label flex-1 rounded-md border border-accent px-4 py-2.5 text-accent hover:bg-accent/10 disabled:opacity-50"
                >
                  {busy === 'ask' ? 'asking' : 'ask'}
                </button>
                <button
                  type="button"
                  onClick={() => void doCapture()}
                  disabled={!text.trim() || busy !== null}
                  className="mono-label flex-1 rounded-md bg-accent px-4 py-2.5 text-black hover:bg-accent-hi disabled:opacity-50"
                >
                  {busy === 'capture' ? 'capturing' : 'capture'}
                </button>
              </div>

              {recording ? (
                <p className="mt-4 flex items-center gap-2 text-sm text-muted">
                  <span
                    aria-hidden
                    className="inline-block h-2 w-2 rounded-full bg-danger"
                    style={{ boxShadow: '0 0 8px var(--danger)' }}
                  />
                  Recording. Tap the voice icon again to stop and transcribe.
                </p>
              ) : null}
              {busy === 'voice' && !recording ? (
                <p className="mt-4 flex items-center gap-2 text-sm text-muted">
                  <span
                    aria-hidden
                    className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-line border-t-accent"
                  />
                  Transcribing voice note.
                </p>
              ) : null}

              {result ? (
                <div className="mt-5 border-t border-line pt-4">
                  <div className="mb-1 flex items-center justify-between">
                    <MonoLabel tone="accent">
                      {result.kind === 'answer'
                        ? 'nexa'
                        : result.kind === 'captured'
                          ? 'captured'
                          : result.kind === 'journaled'
                            ? 'journal'
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
                  ) : result.kind === 'journaled' ? (
                    <p className="text-sm text-cream">
                      Saved to your Journal.{' '}
                      <button
                        type="button"
                        onClick={() => {
                          navigate('journal');
                          close();
                        }}
                        className="text-accent underline-offset-2 hover:underline"
                      >
                        Open Journal
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
