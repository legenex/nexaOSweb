import { useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../../app/client';
import { Button, GlassCard, MonoLabel, Pill } from '../../../components/primitives';
import { useFlow } from '../FlowProvider';

type ProjectMode = Schemas['ProjectModeRead'];

const SOURCES = ['note', 'voice', 'md', 'pdf', 'url', 'youtube', 'image', 'telegram', 'slack'];

// The interactive capture box: a drop target, name and description fields, source chips, a
// project mode selector that drives the questions and destination, a Generate with AI button,
// a details modal, and a Capture button that starts the run.
export function CaptureCard() {
  const { capture, expand } = useFlow();
  const [name, setName] = useState('');
  const [body, setBody] = useState('');
  const [source, setSource] = useState('note');
  const [file, setFile] = useState<File | null>(null);
  const [modes, setModes] = useState<ProjectMode[]>([]);
  const [mode, setMode] = useState('');
  const [busy, setBusy] = useState(false);
  const [expanding, setExpanding] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      const { data } = await api.GET('/projects/modes');
      if (!active || !data) return;
      const list = data as ProjectMode[];
      setModes(list);
      if (list.length > 0) setMode(list[0]!.key);
    })();
    return () => {
      active = false;
    };
  }, []);

  const selectedMode = modes.find((entry) => entry.key === mode) ?? null;

  async function onCapture() {
    if (!name.trim()) {
      setError('A project name is required.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await capture({ name, body, source, mode, file });
      setName('');
      setBody('');
      setFile(null);
    } catch {
      setError('Capture failed.');
    } finally {
      setBusy(false);
    }
  }

  async function onGenerate() {
    setExpanding(true);
    setError(null);
    try {
      const expanded = await expand(name, body);
      if (expanded) setBody(expanded);
    } catch {
      setError('Could not expand. Check the Brain connection.');
    } finally {
      setExpanding(false);
    }
  }

  return (
    <GlassCard>
      <div className="mb-3 flex items-center justify-between">
        <MonoLabel tone="accent">capture</MonoLabel>
        <MonoLabel tone="faint">drop or type</MonoLabel>
      </div>

      <div
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          const dropped = event.dataTransfer.files?.[0];
          if (dropped) {
            setFile(dropped);
            setSource('pdf');
          }
        }}
        className="mb-3 rounded-lg border border-dashed border-line px-3 py-2 text-center"
      >
        <MonoLabel tone="faint">{file ? file.name : 'drop a file'}</MonoLabel>
      </div>

      <input
        aria-label="Project name"
        placeholder="Project name"
        value={name}
        onChange={(event) => setName(event.target.value)}
        className="mb-2 w-full rounded-lg border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent"
      />
      <textarea
        aria-label="Description"
        placeholder="Describe the idea"
        value={body}
        onChange={(event) => setBody(event.target.value)}
        rows={3}
        className="mb-3 w-full resize-none rounded-lg border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent"
      />

      {/* Project mode drives the capture questions and the build destination. */}
      {modes.length > 0 ? (
        <div className="mb-3">
          <MonoLabel tone="faint">build mode</MonoLabel>
          <select
            aria-label="Build mode"
            value={mode}
            onChange={(event) => setMode(event.target.value)}
            className="mt-1 w-full rounded-lg border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent"
          >
            {modes.map((entry) => (
              <option key={entry.key} value={entry.key}>
                {entry.label}
              </option>
            ))}
          </select>
          {selectedMode ? (
            <div className="mt-2 rounded-lg border border-line bg-canvas/60 p-3">
              <div className="flex items-center justify-between">
                <MonoLabel tone="faint">guiding questions</MonoLabel>
                <Pill variant="accent">{selectedMode.build_destination}</Pill>
              </div>
              <ul className="mt-1 list-disc pl-4 text-xs text-muted">
                {selectedMode.capture_questions.map((question) => (
                  <li key={question}>{question}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="mb-3 flex flex-wrap gap-1.5">
        {SOURCES.map((entry) => (
          <button
            key={entry}
            type="button"
            onClick={() => setSource(entry)}
            aria-pressed={entry === source}
            aria-label={`Source ${entry}`}
          >
            <Pill variant={entry === source ? 'solid' : 'grey'}>{entry}</Pill>
          </button>
        ))}
      </div>

      {showDetails ? (
        <div className="mb-3 rounded-lg border border-line bg-canvas/60 p-3">
          <MonoLabel tone="faint">extra context</MonoLabel>
          <textarea
            aria-label="Extra context"
            rows={2}
            placeholder="type, reference links, preferred build target"
            className="mt-1 w-full resize-none rounded-lg border border-line bg-canvas px-3 py-2 text-xs text-cream outline-none focus:border-accent"
          />
        </div>
      ) : null}

      {error ? <p className="mb-2 text-xs text-danger">{error}</p> : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={() => void onCapture()} disabled={busy}>
          {busy ? 'Capturing' : 'Capture'}
        </Button>
        <Button variant="outline" onClick={() => void onGenerate()} disabled={expanding}>
          {expanding ? 'Generating' : 'Generate with AI'}
        </Button>
        <Button variant="muted" onClick={() => setShowDetails((value) => !value)}>
          Details
        </Button>
      </div>
    </GlassCard>
  );
}
