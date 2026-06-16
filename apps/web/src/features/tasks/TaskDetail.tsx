import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { AutonomySelector, normalizeLevel, useProjectAutonomy } from '../../components/autonomy';
import type { AutonomyLevel } from '../../components/autonomy';
import { Button, MonoLabel } from '../../components/primitives';
import { AgentRunPanel } from './AgentRunPanel';

type Task = Schemas['TaskRead'];
type Project = Schemas['ProjectRead'];
type Comment = Schemas['TaskCommentRead'];
type ChecklistItem = Schemas['ChecklistItem'];
type Label = Schemas['TaskLabel'];

type Priority = 'low' | 'med' | 'high';
type Status = 'todo' | 'doing' | 'agent_working' | 'review' | 'done';

const STATUSES: { key: Status; label: string }[] = [
  { key: 'todo', label: 'To do' },
  { key: 'doing', label: 'Doing' },
  { key: 'agent_working', label: 'Agent working' },
  { key: 'review', label: 'Review' },
  { key: 'done', label: 'Done' },
];

const PRIORITIES: { key: Priority; label: string }[] = [
  { key: 'low', label: 'Low' },
  { key: 'med', label: 'Med' },
  { key: 'high', label: 'High' },
];

// Label colors map to the brand palette tokens only, never a raw hex.
export const LABEL_COLORS = ['orange', 'green', 'gold', 'red', 'grey'] as const;
type LabelColor = (typeof LABEL_COLORS)[number];

const LABEL_SWATCH: Record<LabelColor, string> = {
  orange: 'bg-accent',
  green: 'bg-status-green',
  gold: 'bg-gate-gold',
  red: 'bg-danger',
  grey: 'bg-line',
};

const LABEL_PILL: Record<LabelColor, string> = {
  orange: 'border-accent text-accent',
  green: 'border-status-green text-status-green',
  gold: 'border-gate-gold text-gate-gold',
  red: 'border-danger text-danger',
  grey: 'border-line text-muted',
};

export function LabelPill({ label }: { label: Label }) {
  const color = (LABEL_COLORS as readonly string[]).includes(label.color)
    ? (label.color as LabelColor)
    : 'grey';
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-[0.62rem] uppercase tracking-[0.1em] ${LABEL_PILL[color]}`}
    >
      {label.name || color}
    </span>
  );
}

const inputClass =
  'w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent';
const labelClass = 'mono-label mb-1 block text-faint';

function newId(): string {
  // A stable client id for a checklist item. crypto.randomUUID is available in the browser.
  return typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `c${Date.now()}`;
}

export function TaskDetail({
  task,
  projects,
  onClose,
  onChanged,
}: {
  task: Task;
  projects: Project[];
  onClose: () => void;
  onChanged: () => void;
}) {
  // Core editable fields persist together on Save; labels, checklist, and comments persist
  // immediately as they change, the way a Trello card behaves.
  const [title, setTitle] = useState(task.title);
  const [detail, setDetail] = useState(task.detail ?? '');
  const [goal, setGoal] = useState(task.goal_for_agent ?? '');
  const [projectId, setProjectId] = useState<number | null>(task.project_id);
  const [timeline, setTimeline] = useState(task.timeline ?? '');
  const [priority, setPriority] = useState<Priority>((task.priority as Priority) ?? 'med');
  const [status, setStatus] = useState<Status>((task.status as Status) ?? 'todo');
  const [hasDue, setHasDue] = useState(Boolean(task.due_date));
  const [due, setDue] = useState(task.due_date ?? '');
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(false);

  const [labels, setLabels] = useState<Label[]>(task.labels ?? []);
  const [checklist, setChecklist] = useState<ChecklistItem[]>(task.checklist ?? []);
  const [newItem, setNewItem] = useState('');
  const [newLabelName, setNewLabelName] = useState('');

  const [comments, setComments] = useState<Comment[] | null>(null);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [generating, setGenerating] = useState(false);

  // Per task autonomy. TaskRead now projects the stored task level, so a reopen shows the real per
  // task level, including an override set earlier through the AB4.3 endpoint. The project default,
  // read here, is shown only as context for what the task inherited from.
  const projectAutonomy = useProjectAutonomy(projectId);
  const [taskLevel, setTaskLevel] = useState<AutonomyLevel>(normalizeLevel(task.autonomy));
  const [autonomyBusy, setAutonomyBusy] = useState(false);
  const effectiveLevel: AutonomyLevel = taskLevel;
  // Resync when the dialog is reused for a different task: read that task's stored level.
  useEffect(() => {
    setTaskLevel(normalizeLevel(task.autonomy));
  }, [task.id, task.autonomy]);

  const setAutonomy = async (level: AutonomyLevel) => {
    setTaskLevel(level);
    setAutonomyBusy(true);
    try {
      await api.PUT('/agents/tasks/{task_id}/autonomy', {
        params: { path: { task_id: task.id } },
        body: { level },
      });
    } finally {
      setAutonomyBusy(false);
    }
  };

  const patch = useCallback(
    async (body: Record<string, unknown>) => {
      await api.PATCH('/tasks/{task_id}', {
        params: { path: { task_id: task.id } },
        body,
      });
      onChanged();
    },
    [task.id, onChanged],
  );

  const loadComments = useCallback(async () => {
    const { data } = await api.GET('/tasks/{task_id}/comments', {
      params: { path: { task_id: task.id } },
    });
    setComments((data as Comment[]) ?? []);
  }, [task.id]);

  useEffect(() => {
    void loadComments();
  }, [loadComments]);

  const saveCore = async () => {
    if (!title.trim()) return;
    setSaving(true);
    try {
      await patch({
        title: title.trim(),
        detail: detail.trim() || null,
        goal_for_agent: goal.trim() || null,
        timeline: timeline.trim() || null,
        project_id: projectId,
        status,
        priority,
        due_date: hasDue && due ? due : null,
      });
      setSavedAt(true);
      window.setTimeout(() => setSavedAt(false), 1500);
    } finally {
      setSaving(false);
    }
  };

  const generate = async () => {
    const seed = title.trim() || detail.trim();
    if (!seed) return;
    setGenerating(true);
    try {
      const { data, error } = await api.POST('/tasks/generate', { body: { prompt: seed } });
      if (!error && data) {
        const d = data as Schemas['TaskDraft'];
        if (d.notes) setDetail(d.notes);
        if (d.goal_for_agent) setGoal(d.goal_for_agent);
        if (d.timeline) setTimeline(d.timeline);
        if (PRIORITIES.some((p) => p.key === d.priority)) setPriority(d.priority as Priority);
      }
    } finally {
      setGenerating(false);
    }
  };

  // --- labels ---
  const hasLabel = (color: LabelColor, name: string) =>
    labels.some((l) => l.color === color && (l.name || '') === name);

  const toggleColorLabel = (color: LabelColor) => {
    // Toggle a plain color label (no name). Named labels are added separately.
    const next = hasLabel(color, '')
      ? labels.filter((l) => !(l.color === color && (l.name || '') === ''))
      : [...labels, { name: '', color }];
    setLabels(next);
    void patch({ labels: next });
  };

  const addNamedLabel = (color: LabelColor) => {
    const name = newLabelName.trim();
    if (!name || hasLabel(color, name)) return;
    const next = [...labels, { name, color }];
    setLabels(next);
    setNewLabelName('');
    void patch({ labels: next });
  };

  const removeLabel = (index: number) => {
    const next = labels.filter((_, i) => i !== index);
    setLabels(next);
    void patch({ labels: next });
  };

  // --- checklist ---
  const persistChecklist = (next: ChecklistItem[]) => {
    setChecklist(next);
    void patch({ checklist: next });
  };

  const addChecklistItem = () => {
    const text = newItem.trim();
    if (!text) return;
    persistChecklist([...checklist, { id: newId(), text, done: false }]);
    setNewItem('');
  };

  const toggleItem = (id: string) =>
    persistChecklist(checklist.map((i) => (i.id === id ? { ...i, done: !i.done } : i)));

  const removeItem = (id: string) =>
    persistChecklist(checklist.filter((i) => i.id !== id));

  const doneCount = checklist.filter((i) => i.done).length;

  // --- comments ---
  const sendComment = async () => {
    const body = draft.trim();
    if (!body) return;
    setSending(true);
    try {
      await api.POST('/tasks/{task_id}/comments', {
        params: { path: { task_id: task.id } },
        body: { body },
      });
      setDraft('');
      await loadComments();
    } finally {
      setSending(false);
    }
  };

  const deleteComment = async (id: number) => {
    await api.DELETE('/tasks/{task_id}/comments/{comment_id}', {
      params: { path: { task_id: task.id, comment_id: id } },
    });
    await loadComments();
  };

  return (
    <div className="space-y-4">
      {/* core fields */}
      <div>
        <label className={labelClass} htmlFor="d-title">
          title
        </label>
        <input
          id="d-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className={inputClass}
        />
      </div>

      <div>
        <label className={labelClass} htmlFor="d-detail">
          description
        </label>
        <textarea
          id="d-detail"
          value={detail}
          onChange={(e) => setDetail(e.target.value)}
          rows={3}
          placeholder="Add a more detailed description..."
          className={`resize-none ${inputClass}`}
        />
      </div>

      <div>
        <label className={labelClass} htmlFor="d-goal">
          goal for the agent
        </label>
        <textarea
          id="d-goal"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          rows={2}
          className={`resize-none ${inputClass}`}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass} htmlFor="d-project">
            project
          </label>
          <select
            id="d-project"
            value={projectId === null ? '' : String(projectId)}
            onChange={(e) => setProjectId(e.target.value === '' ? null : Number(e.target.value))}
            className={inputClass}
          >
            <option value="">None</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={labelClass} htmlFor="d-timeline">
            timeline
          </label>
          <input
            id="d-timeline"
            value={timeline}
            onChange={(e) => setTimeline(e.target.value)}
            placeholder="e.g. this week"
            className={inputClass}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass} htmlFor="d-priority">
            priority
          </label>
          <select
            id="d-priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value as Priority)}
            className={inputClass}
          >
            {PRIORITIES.map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={labelClass} htmlFor="d-status">
            status
          </label>
          <select
            id="d-status"
            value={status}
            onChange={(e) => setStatus(e.target.value as Status)}
            className={inputClass}
          >
            {STATUSES.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="flex items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            checked={hasDue}
            onChange={(e) => setHasDue(e.target.checked)}
            className="accent-accent"
          />
          Has due date
        </label>
        {hasDue ? (
          <input
            type="date"
            value={due ?? ''}
            onChange={(e) => setDue(e.target.value)}
            className={`mt-2 ${inputClass}`}
          />
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={() => void saveCore()} disabled={saving || !title.trim()}>
          {saving ? 'saving' : 'Save'}
        </Button>
        <Button
          variant="outline"
          onClick={() => void generate()}
          disabled={generating || (!title.trim() && !detail.trim())}
        >
          {generating ? 'generating' : 'Generate with AI'}
        </Button>
        {savedAt ? <span className="mono-meta text-status-green">saved</span> : null}
      </div>

      {/* labels */}
      <div className="border-t border-line pt-4">
        <MonoLabel tone="faint">labels</MonoLabel>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {labels.length === 0 ? <span className="mono-meta text-faint">none</span> : null}
          {labels.map((label, index) => (
            <button
              key={`${label.color}-${label.name}-${index}`}
              type="button"
              onClick={() => removeLabel(index)}
              title="Remove label"
              className="group"
            >
              <LabelPill label={label} />
            </button>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {LABEL_COLORS.map((color) => (
            <button
              key={color}
              type="button"
              onClick={() => toggleColorLabel(color)}
              aria-label={`toggle ${color} label`}
              className={`h-6 w-6 rounded-md ring-1 ring-line transition hover:scale-110 ${LABEL_SWATCH[color]} ${
                hasLabel(color, '') ? 'ring-2 ring-cream' : ''
              }`}
            />
          ))}
        </div>
        <div className="mt-2 flex items-center gap-2">
          <input
            value={newLabelName}
            onChange={(e) => setNewLabelName(e.target.value)}
            placeholder="name a label, then pick a color"
            className={inputClass}
          />
          {LABEL_COLORS.map((color) => (
            <button
              key={`named-${color}`}
              type="button"
              onClick={() => addNamedLabel(color)}
              aria-label={`add ${color} named label`}
              className={`h-5 w-5 shrink-0 rounded ${LABEL_SWATCH[color]} ${
                newLabelName.trim() ? 'opacity-100' : 'opacity-40'
              }`}
            />
          ))}
        </div>
      </div>

      {/* checklist */}
      <div className="border-t border-line pt-4">
        <div className="flex items-center justify-between">
          <MonoLabel tone="faint">checklist</MonoLabel>
          {checklist.length > 0 ? (
            <span className="mono-meta text-faint">
              {doneCount}/{checklist.length}
            </span>
          ) : null}
        </div>
        <ul className="mt-2 space-y-1.5">
          {checklist.map((item) => (
            <li key={item.id} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={item.done}
                onChange={() => toggleItem(item.id)}
                className="accent-accent"
              />
              <span className={`flex-1 text-sm ${item.done ? 'text-faint line-through' : 'text-cream'}`}>
                {item.text}
              </span>
              <button
                type="button"
                onClick={() => removeItem(item.id)}
                aria-label="remove item"
                className="mono-label text-faint hover:text-danger"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-2 flex items-center gap-2">
          <input
            value={newItem}
            onChange={(e) => setNewItem(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addChecklistItem();
              }
            }}
            placeholder="Add a checklist item..."
            className={inputClass}
          />
          <Button variant="muted" onClick={addChecklistItem} disabled={!newItem.trim()}>
            add
          </Button>
        </div>
      </div>

      {/* per task autonomy: green runs unattended, yellow gates, red never auto runs */}
      <div className="border-t border-line pt-4">
        <AutonomySelector
          label="agent autonomy"
          value={effectiveLevel}
          onChange={(level) => void setAutonomy(level)}
          busy={autonomyBusy}
          hint={
            projectAutonomy.state
              ? `Project default is ${projectAutonomy.state.default_level}. This task is set to ${effectiveLevel}.`
              : undefined
          }
        />
      </div>

      {/* agent build: send to agent, then the gated run review */}
      <AgentRunPanel task={task} onChanged={onChanged} />

      {/* comments / activity */}
      <div className="border-t border-line pt-4">
        <MonoLabel tone="faint">activity</MonoLabel>
        <div className="mt-2 flex items-center gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                void sendComment();
              }
            }}
            placeholder="Write a comment..."
            className={inputClass}
          />
          <Button variant="primary" onClick={() => void sendComment()} disabled={sending || !draft.trim()}>
            send
          </Button>
        </div>
        <ul className="mt-3 space-y-2">
          {comments === null ? (
            <li className="mono-meta text-faint">loading…</li>
          ) : comments.length === 0 ? (
            <li className="mono-meta text-faint">No activity yet.</li>
          ) : (
            comments.map((comment) => (
              <li key={comment.id} className="rounded-md border border-line p-2">
                <div className="flex items-center justify-between">
                  <span className="mono-meta text-accent">{comment.author}</span>
                  <button
                    type="button"
                    onClick={() => void deleteComment(comment.id)}
                    aria-label="delete comment"
                    className="mono-label text-faint hover:text-danger"
                  >
                    ✕
                  </button>
                </div>
                <p className="mt-1 whitespace-pre-wrap text-sm text-cream">{comment.body}</p>
              </li>
            ))
          )}
        </ul>
      </div>

      <div className="flex justify-end border-t border-line pt-3">
        <button
          type="button"
          onClick={onClose}
          className="mono-label rounded-md border border-line px-3 py-1 hover:text-cream"
        >
          close
        </button>
      </div>
    </div>
  );
}
