import { useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { Button, MonoLabel, Modal } from '../../components/primitives';

type ResearchProject = Schemas['ResearchProjectRead'];

type Depth = 'quick' | 'standard' | 'deep';
type Schedule = 'off' | 'daily' | 'weekly';

const DEPTHS: Depth[] = ['quick', 'standard', 'deep'];
const SCHEDULES: Schedule[] = ['off', 'daily', 'weekly'];

const field =
  'w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent';

interface DialogProps {
  open: boolean;
  initial?: ResearchProject | null;
  onClose: () => void;
  onSaved: () => void;
}

// The new and edit research project dialog. Generate with AI drafts purpose, goals, depth,
// lookback, and schedule from the topic, ready to edit, before Create or Save.
export function ResearchProjectDialog({ open, initial, onClose, onSaved }: DialogProps) {
  const editing = Boolean(initial);
  const [name, setName] = useState(initial?.name ?? '');
  const [topic, setTopic] = useState(initial?.topic ?? '');
  const [purpose, setPurpose] = useState(initial?.purpose ?? '');
  const [goals, setGoals] = useState<string[]>(initial?.goals ?? []);
  const [goalDraft, setGoalDraft] = useState('');
  const [depth, setDepth] = useState<Depth>((initial?.depth as Depth) ?? 'standard');
  const [lookback, setLookback] = useState(initial?.lookback ?? 30);
  const [schedule, setSchedule] = useState<Schedule>((initial?.schedule as Schedule) ?? 'off');
  const [category, setCategory] = useState(initial?.category ?? 'general');
  const [busy, setBusy] = useState<'generate' | 'save' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const addGoal = () => {
    const value = goalDraft.trim();
    if (!value) return;
    setGoals((current) => [...current, value]);
    setGoalDraft('');
  };

  const generate = async () => {
    if (!topic.trim()) return;
    setBusy('generate');
    setError(null);
    try {
      const { data, error: err } = await api.POST('/research/generate-config', {
        body: { topic: topic.trim(), name: name.trim() },
      });
      if (err || !data) throw new Error('generate failed');
      setPurpose(data.purpose);
      setGoals(data.goals);
      setDepth(data.depth as Depth);
      setLookback(data.lookback);
      setSchedule(data.schedule as Schedule);
    } catch {
      setError('Could not draft a config. Check the Brain connection.');
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    if (!name.trim()) {
      setError('A name is required.');
      return;
    }
    setBusy('save');
    setError(null);
    const body = {
      name: name.trim(),
      topic: topic.trim(),
      purpose,
      goals,
      depth,
      lookback,
      schedule,
      category: category.trim() || 'general',
    };
    try {
      if (editing && initial) {
        const { error: err } = await api.PATCH('/research/projects/{research_id}', {
          params: { path: { research_id: initial.id } },
          body,
        });
        if (err) throw new Error('save failed');
      } else {
        const { error: err } = await api.POST('/research/projects', { body });
        if (err) throw new Error('create failed');
      }
      onSaved();
      onClose();
    } catch {
      setError('Could not save the research project.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <Modal open={open} title={editing ? 'edit research project' : 'new research project'} onClose={onClose}>
      <div className="space-y-3">
        <div>
          <MonoLabel tone="faint">name</MonoLabel>
          <input className={`mt-1 ${field}`} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <MonoLabel tone="faint">research topic</MonoLabel>
          <input
            className={`mt-1 ${field}`}
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="What to research"
          />
        </div>

        <Button variant="outline" onClick={() => void generate()} disabled={!topic.trim() || busy !== null}>
          {busy === 'generate' ? 'drafting' : 'Generate with AI'}
        </Button>

        <div>
          <MonoLabel tone="faint">purpose</MonoLabel>
          <textarea
            rows={2}
            className={`mt-1 resize-none ${field}`}
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
          />
        </div>

        <div>
          <MonoLabel tone="faint">goals</MonoLabel>
          <div className="mt-1 flex gap-2">
            <input
              className={field}
              value={goalDraft}
              onChange={(e) => setGoalDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  addGoal();
                }
              }}
              placeholder="Add a goal"
            />
            <Button variant="muted" onClick={addGoal} disabled={!goalDraft.trim()}>
              add
            </Button>
          </div>
          {goals.length > 0 ? (
            <ul className="mt-2 space-y-1">
              {goals.map((goal, index) => (
                <li
                  key={`${goal}-${index}`}
                  className="flex items-center justify-between rounded-md border border-line px-3 py-1.5 text-sm text-cream"
                >
                  <span>{goal}</span>
                  <button
                    type="button"
                    aria-label={`Remove ${goal}`}
                    onClick={() => setGoals((current) => current.filter((_, i) => i !== index))}
                    className="mono-label text-muted hover:text-accent"
                  >
                    remove
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <MonoLabel tone="faint">depth</MonoLabel>
            <select className={`mt-1 ${field}`} value={depth} onChange={(e) => setDepth(e.target.value as Depth)}>
              {DEPTHS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>
          <div>
            <MonoLabel tone="faint">lookback (days)</MonoLabel>
            <input
              type="number"
              min={1}
              max={3650}
              className={`mt-1 ${field}`}
              value={lookback}
              onChange={(e) => setLookback(Math.max(1, Number(e.target.value) || 1))}
            />
          </div>
          <div>
            <MonoLabel tone="faint">schedule</MonoLabel>
            <select
              className={`mt-1 ${field}`}
              value={schedule}
              onChange={(e) => setSchedule(e.target.value as Schedule)}
            >
              {SCHEDULES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <MonoLabel tone="faint">category</MonoLabel>
          <input
            className={`mt-1 ${field}`}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          />
        </div>

        {error ? <p className="text-xs text-danger">{error}</p> : null}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="muted" onClick={onClose} disabled={busy !== null}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void save()} disabled={!name.trim() || busy !== null}>
            {busy === 'save' ? 'saving' : editing ? 'Save' : 'Create'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
