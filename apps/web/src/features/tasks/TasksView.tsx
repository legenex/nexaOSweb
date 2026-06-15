import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { Button, GlassCard, Modal, MonoLabel, Pill } from '../../components/primitives';
import { OverflowMenu } from '../../components/OverflowMenu';
import { ConfirmDialog } from '../projects/workspace/ConfirmDialog';

type Task = Schemas['TaskRead'];
type Project = Schemas['ProjectRead'];
type NewFinding = Schemas['NewFindingRead'];

// The Hermes board columns, in order. The Brain validates this set. agent_working is also
// surfaced automatically for a task whose run is live; a legacy blocked task folds into Doing.
type Status = 'todo' | 'doing' | 'agent_working' | 'review' | 'done';
type Priority = 'low' | 'med' | 'high';

const COLUMNS: { key: Status; label: string }[] = [
  { key: 'todo', label: 'To do' },
  { key: 'doing', label: 'Doing' },
  { key: 'agent_working', label: 'Agent working' },
  { key: 'review', label: 'Review' },
  { key: 'done', label: 'Done' },
];

const STATUS_LABEL: Record<Status, string> = Object.fromEntries(
  COLUMNS.map((c) => [c.key, c.label]),
) as Record<Status, string>;

const PRIORITIES: { key: Priority; label: string }[] = [
  { key: 'low', label: 'Low' },
  { key: 'med', label: 'Med' },
  { key: 'high', label: 'High' },
];

// The board column a task belongs in. A live run wins (Agent working); a legacy blocked task
// folds into Doing; anything off board (e.g. archived) returns null and is not shown.
function columnFor(task: Task): Status | null {
  if (task.agent_active) return 'agent_working';
  if (task.status === 'blocked') return 'doing';
  return (COLUMNS.find((c) => c.key === task.status)?.key as Status) ?? null;
}

// Friendly names for how a task was created. Manual tasks carry no provenance pill.
const SOURCE_LABEL: Record<string, string> = {
  research: 'from research',
  run: 'from a run',
};

const inputClass =
  'w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent';
const labelClass = 'mono-label mb-1 block text-faint';

// 'all' is the cross project view; a number scopes the board to one project.
type ProjectFilter = number | 'all';
type ViewMode = 'board' | 'list';

// --- task form (shared by the New Task dialog and the editor) --------------------------------

interface TaskFormValues {
  title: string;
  detail: string;
  goal_for_agent: string;
  project_id: number | null;
  timeline: string;
  priority: Priority;
  status: Status;
  due_date: string | null;
}

function TaskForm({
  initial,
  projects,
  showStatus,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial: Partial<TaskFormValues>;
  projects: Project[];
  showStatus: boolean;
  submitLabel: string;
  onSubmit: (values: TaskFormValues) => Promise<void>;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(initial.title ?? '');
  const [detail, setDetail] = useState(initial.detail ?? '');
  const [goal, setGoal] = useState(initial.goal_for_agent ?? '');
  const [projectId, setProjectId] = useState<number | null>(initial.project_id ?? null);
  const [timeline, setTimeline] = useState(initial.timeline ?? '');
  const [priority, setPriority] = useState<Priority>((initial.priority as Priority) ?? 'med');
  const [status, setStatus] = useState<Status>((initial.status as Status) ?? 'todo');
  const [hasDue, setHasDue] = useState(Boolean(initial.due_date));
  const [due, setDue] = useState(initial.due_date ?? '');
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);

  const generate = async () => {
    const seed = title.trim() || detail.trim();
    if (!seed) return;
    setGenerating(true);
    try {
      const { data, error } = await api.POST('/tasks/generate', { body: { prompt: seed } });
      if (!error && data) {
        const draft = data as Schemas['TaskDraft'];
        if (!title.trim() && draft.title) setTitle(draft.title);
        if (draft.notes) setDetail(draft.notes);
        if (draft.goal_for_agent) setGoal(draft.goal_for_agent);
        if (draft.timeline) setTimeline(draft.timeline);
        if (PRIORITIES.some((p) => p.key === draft.priority)) setPriority(draft.priority as Priority);
      }
    } finally {
      setGenerating(false);
    }
  };

  const submit = async () => {
    if (!title.trim()) return;
    setBusy(true);
    try {
      await onSubmit({
        title: title.trim(),
        detail: detail.trim(),
        goal_for_agent: goal.trim(),
        project_id: projectId,
        timeline: timeline.trim(),
        priority,
        status,
        due_date: hasDue && due ? due : null,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <label className={labelClass} htmlFor="task-title">
          title
        </label>
        <input
          id="task-title"
          value={title}
          autoFocus
          onChange={(event) => setTitle(event.target.value)}
          placeholder="What needs doing?"
          className={inputClass}
        />
      </div>

      <div>
        <label className={labelClass} htmlFor="task-notes">
          notes
        </label>
        <textarea
          id="task-notes"
          value={detail}
          onChange={(event) => setDetail(event.target.value)}
          rows={3}
          placeholder="Context, links, anything useful (optional)."
          className={`resize-none ${inputClass}`}
        />
      </div>

      <div>
        <label className={labelClass} htmlFor="task-goal">
          goal for the agent
        </label>
        <textarea
          id="task-goal"
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          rows={2}
          placeholder="What should an agent achieve to complete this (optional)."
          className={`resize-none ${inputClass}`}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass} htmlFor="task-project">
            project
          </label>
          <select
            id="task-project"
            value={projectId === null ? '' : String(projectId)}
            onChange={(event) =>
              setProjectId(event.target.value === '' ? null : Number(event.target.value))
            }
            className={inputClass}
          >
            <option value="">None</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={labelClass} htmlFor="task-timeline">
            timeline
          </label>
          <input
            id="task-timeline"
            value={timeline}
            onChange={(event) => setTimeline(event.target.value)}
            placeholder="e.g. this week"
            className={inputClass}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass} htmlFor="task-priority">
            priority
          </label>
          <select
            id="task-priority"
            value={priority}
            onChange={(event) => setPriority(event.target.value as Priority)}
            className={inputClass}
          >
            {PRIORITIES.map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        {showStatus ? (
          <div>
            <label className={labelClass} htmlFor="task-status">
              status
            </label>
            <select
              id="task-status"
              value={status}
              onChange={(event) => setStatus(event.target.value as Status)}
              className={inputClass}
            >
              {COLUMNS.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div />
        )}
      </div>

      <div>
        <label className="flex items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            checked={hasDue}
            onChange={(event) => setHasDue(event.target.checked)}
            className="accent-accent"
          />
          Has due date
        </label>
        {hasDue ? (
          <input
            type="date"
            value={due ?? ''}
            onChange={(event) => setDue(event.target.value)}
            className={`mt-2 ${inputClass}`}
          />
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Button variant="primary" onClick={() => void submit()} disabled={busy || !title.trim()}>
          {busy ? 'saving' : submitLabel}
        </Button>
        <Button
          variant="outline"
          onClick={() => void generate()}
          disabled={generating || (!title.trim() && !detail.trim())}
        >
          {generating ? 'generating' : 'Generate with AI'}
        </Button>
        <button
          type="button"
          onClick={onCancel}
          className="mono-label rounded-md border border-line px-3 py-1 hover:text-cream"
        >
          cancel
        </button>
      </div>
    </div>
  );
}

// --- pull from research picker ---------------------------------------------------------------

function ResearchPicker({
  open,
  onClose,
  onPulled,
}: {
  open: boolean;
  onClose: () => void;
  onPulled: () => void;
}) {
  const [findings, setFindings] = useState<NewFinding[] | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setFindings(null);
    setSelected(new Set());
    void (async () => {
      const { data } = await api.GET('/research/findings/new');
      setFindings((data as NewFinding[]) ?? []);
    })();
  }, [open]);

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const pull = async () => {
    if (selected.size === 0) return;
    setBusy(true);
    try {
      for (const id of selected) {
        await api.POST('/research/findings/{finding_id}/to-task', {
          params: { path: { finding_id: id } },
        });
      }
      onPulled();
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} title="pull from research" onClose={onClose}>
      {findings === null ? (
        <p className="text-sm text-muted">Loading findings…</p>
      ) : findings.length === 0 ? (
        <p className="text-sm text-muted">No new research findings to pull right now.</p>
      ) : (
        <>
          <ul className="max-h-80 space-y-2 overflow-y-auto">
            {findings.map((finding) => (
              <li key={finding.id}>
                <label className="flex cursor-pointer items-start gap-3 rounded-md border border-line p-3 hover:border-accent">
                  <input
                    type="checkbox"
                    checked={selected.has(finding.id)}
                    onChange={() => toggle(finding.id)}
                    className="mt-1 accent-accent"
                  />
                  <span className="min-w-0">
                    <span className="block text-sm text-cream">{finding.title}</span>
                    {finding.detail ? (
                      <span className="mt-0.5 block truncate text-xs text-muted">
                        {finding.detail}
                      </span>
                    ) : null}
                    <Pill variant="grey">{finding.research_project_name}</Pill>
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex items-center gap-2">
            <Button variant="primary" onClick={() => void pull()} disabled={busy || selected.size === 0}>
              {busy ? 'pulling' : `Add ${selected.size || ''} as tasks`.trim()}
            </Button>
            <button
              type="button"
              onClick={onClose}
              className="mono-label rounded-md border border-line px-3 py-1 hover:text-cream"
            >
              cancel
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}

// --- task card ------------------------------------------------------------------------------

function PriorityPill({ priority }: { priority: string }) {
  // Med is the default and carries no pill, so the board stays calm; low and high are flagged.
  if (priority === 'high') return <Pill variant="solid">high priority</Pill>;
  if (priority === 'low') return <Pill variant="grey">low priority</Pill>;
  return null;
}

function TaskCard({
  task,
  projectName,
  onMove,
  onEdit,
  onDelete,
  onOpenRun,
}: {
  task: Task;
  projectName: string | null;
  onMove: (status: Status) => void;
  onEdit: () => void;
  onDelete: () => void;
  onOpenRun: (runId: number) => void;
}) {
  const status = columnFor(task) ?? 'todo';
  // Status moves offered in the menu: every column except the current one.
  const moveItems = COLUMNS.filter((c) => c.key !== status).map((c) => ({
    label: `Move to ${c.label}`,
    onClick: () => onMove(c.key),
  }));

  return (
    <GlassCard
      className={`border-electric ${task.agent_active ? 'border-electric-on border border-line' : ''}`}
    >
      <div
        draggable
        onDragStart={(event) => event.dataTransfer.setData('text/task-id', String(task.id))}
        className="cursor-grab active:cursor-grabbing"
      >
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm text-cream">{task.title}</p>
          <OverflowMenu
            label={`Actions for ${task.title}`}
            items={[
              { label: 'Edit', onClick: onEdit },
              ...moveItems,
              { label: 'Delete', danger: true, onClick: onDelete },
            ]}
          />
        </div>
        {task.detail ? (
          <p className="mt-1 whitespace-pre-wrap text-xs text-muted">{task.detail}</p>
        ) : null}
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <PriorityPill priority={task.priority} />
          {task.due_date ? <Pill variant="grey">due {task.due_date}</Pill> : null}
          {task.timeline ? <Pill variant="grey">{task.timeline}</Pill> : null}
          {projectName ? <Pill variant="grey">{projectName}</Pill> : null}
          {SOURCE_LABEL[task.source] ? (
            <Pill variant="green">{SOURCE_LABEL[task.source]}</Pill>
          ) : null}
        </div>
      </div>
      {task.agent_active && task.run_id ? (
        <button
          type="button"
          onClick={() => onOpenRun(task.run_id!)}
          className="mono-label mt-3 rounded-md border border-accent px-3 py-1 text-accent hover:bg-accent/10"
        >
          live · run #{task.run_id} timeline
        </button>
      ) : status !== 'done' ? (
        <button
          type="button"
          onClick={() => onMove('done')}
          className="mono-label mt-3 rounded-md border border-line px-3 py-1 hover:text-accent"
        >
          ✓ complete
        </button>
      ) : (
        <button
          type="button"
          onClick={() => onMove('todo')}
          className="mono-label mt-3 rounded-md border border-line px-3 py-1 hover:text-accent"
        >
          reopen
        </button>
      )}
    </GlassCard>
  );
}

// --- board ----------------------------------------------------------------------------------

function Column({
  columnKey,
  label,
  tasks,
  projectNameFor,
  onMove,
  onEdit,
  onDelete,
  onOpenRun,
  onDropTask,
}: {
  columnKey: Status;
  label: string;
  tasks: Task[];
  projectNameFor: (id: number | null) => string | null;
  onMove: (task: Task, status: Status) => void;
  onEdit: (task: Task) => void;
  onDelete: (task: Task) => void;
  onOpenRun: (runId: number) => void;
  onDropTask: (taskId: number, status: Status) => void;
}) {
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        const id = Number(event.dataTransfer.getData('text/task-id'));
        if (id) onDropTask(id, columnKey);
      }}
      className={`flex w-72 shrink-0 flex-col gap-3 rounded-glass p-1 transition ${
        over ? 'bg-accent/5 ring-1 ring-accent/40' : ''
      }`}
    >
      <div className="flex items-center justify-between border-b border-line pb-2">
        <MonoLabel tone="faint">{label}</MonoLabel>
        <span className="mono-meta text-faint">{tasks.length}</span>
      </div>
      {tasks.length === 0 ? (
        <p className="mono-meta text-faint">Nothing here.</p>
      ) : (
        tasks.map((task) => (
          <TaskCard
            key={task.id}
            task={task}
            projectName={projectNameFor(task.project_id)}
            onMove={(status) => onMove(task, status)}
            onEdit={() => onEdit(task)}
            onDelete={() => onDelete(task)}
            onOpenRun={onOpenRun}
          />
        ))
      )}
    </div>
  );
}

// A compact, read only run timeline opened from a run linked task in Agent working.
function RunTimelineModal({ runId, onClose }: { runId: number | null; onClose: () => void }) {
  const [steps, setSteps] = useState<Schemas['StepRead'][] | null>(null);
  const [runStatus, setRunStatus] = useState<string>('');

  useEffect(() => {
    if (runId === null) return;
    setSteps(null);
    void (async () => {
      const run = await api.GET('/runtime/runs/{run_id}', { params: { path: { run_id: runId } } });
      if (run.data) setRunStatus((run.data as Schemas['RunRead']).status);
      const res = await api.GET('/runtime/runs/{run_id}/steps', {
        params: { path: { run_id: runId } },
      });
      if (res.data) setSteps(res.data as Schemas['StepRead'][]);
    })();
  }, [runId]);

  return (
    <Modal open={runId !== null} title={`run #${runId ?? ''} timeline`} onClose={onClose}>
      {runStatus ? (
        <p className="mb-3">
          <Pill variant="accent">{runStatus}</Pill>
        </p>
      ) : null}
      {steps === null ? (
        <p className="text-sm text-muted">Loading the run timeline…</p>
      ) : steps.length === 0 ? (
        <p className="text-sm text-muted">No steps recorded yet.</p>
      ) : (
        <ol className="space-y-2">
          {steps.map((step) => (
            <li key={step.id} className="flex items-center justify-between gap-3 text-sm">
              <span className="text-cream">
                <span className="mono-meta text-faint">{step.kind}</span> {step.title}
              </span>
              <Pill variant="grey">{step.status}</Pill>
            </li>
          ))}
        </ol>
      )}
    </Modal>
  );
}

// --- list view ------------------------------------------------------------------------------

function ListView({
  tasks,
  projectNameFor,
  onEdit,
}: {
  tasks: Task[];
  projectNameFor: (id: number | null) => string | null;
  onEdit: (task: Task) => void;
}) {
  return (
    <div className="space-y-2">
      {tasks.map((task) => {
        const column = columnFor(task) ?? 'todo';
        return (
          <button
            key={task.id}
            type="button"
            onClick={() => onEdit(task)}
            className="flex w-full items-center justify-between gap-3 rounded-md border border-line px-3 py-2 text-left hover:border-accent"
          >
            <span className="min-w-0">
              <span className="block truncate text-sm text-cream">{task.title}</span>
              <span className="mono-meta text-faint">{STATUS_LABEL[column]}</span>
            </span>
            <span className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
              <PriorityPill priority={task.priority} />
              {task.due_date ? <Pill variant="grey">due {task.due_date}</Pill> : null}
              {projectNameFor(task.project_id) ? (
                <Pill variant="grey">{projectNameFor(task.project_id)}</Pill>
              ) : null}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// --- view -----------------------------------------------------------------------------------

export function TasksView() {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [tasksError, setTasksError] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [filter, setFilter] = useState<ProjectFilter>('all');
  const [view, setView] = useState<ViewMode>('board');

  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Task | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [openRunId, setOpenRunId] = useState<number | null>(null);
  const [pulling, setPulling] = useState(false);
  const [quickTitle, setQuickTitle] = useState('');

  const loadTasks = useCallback(async (scope: ProjectFilter) => {
    const { data, error } =
      scope === 'all'
        ? await api.GET('/tasks')
        : await api.GET('/tasks', { params: { query: { project_id: scope } } });
    if (error || !data) {
      setTasksError(true);
      setTasks(null);
      return;
    }
    setTasksError(false);
    setTasks(data as Task[]);
  }, []);

  const loadProjects = useCallback(async () => {
    const { data } = await api.GET('/projects');
    if (data) setProjects(data as Project[]);
  }, []);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    setTasks(null);
    void loadTasks(filter);
  }, [filter, loadTasks]);

  const projectNameFor = useCallback(
    (id: number | null) => projects.find((p) => p.id === id)?.name ?? null,
    [projects],
  );

  const byStatus = useMemo(() => {
    const map: Record<Status, Task[]> = {
      todo: [],
      doing: [],
      agent_working: [],
      review: [],
      done: [],
    };
    for (const task of tasks ?? []) {
      const column = columnFor(task);
      if (column) map[column].push(task);
    }
    return map;
  }, [tasks]);

  const move = async (task: Task, status: Status, position?: number) => {
    const { error } = await api.PATCH('/tasks/{task_id}', {
      params: { path: { task_id: task.id } },
      body: position === undefined ? { status } : { status, position },
    });
    if (!error) void loadTasks(filter);
  };

  // A drop onto a column moves the dragged task to that status and appends it to the end.
  const moveById = (taskId: number, status: Status) => {
    const task = (tasks ?? []).find((entry) => entry.id === taskId);
    if (!task) return;
    const endPosition = (byStatus[status]?.length ?? 0) + 1;
    void move(task, status, endPosition);
  };

  const createTask = async (values: TaskFormValues) => {
    const { error } = await api.POST('/tasks', {
      body: {
        title: values.title,
        detail: values.detail || null,
        goal_for_agent: values.goal_for_agent || null,
        timeline: values.timeline || null,
        project_id: values.project_id,
        status: values.status,
        priority: values.priority,
        due_date: values.due_date,
      },
    });
    if (!error) {
      setCreating(false);
      void loadTasks(filter);
    }
  };

  const saveTask = async (task: Task, values: TaskFormValues) => {
    const { error } = await api.PATCH('/tasks/{task_id}', {
      params: { path: { task_id: task.id } },
      body: {
        title: values.title,
        detail: values.detail || null,
        goal_for_agent: values.goal_for_agent || null,
        timeline: values.timeline || null,
        project_id: values.project_id,
        status: values.status,
        priority: values.priority,
        due_date: values.due_date,
      },
    });
    if (!error) {
      setEditing(null);
      void loadTasks(filter);
    }
  };

  const quickAdd = async () => {
    const title = quickTitle.trim();
    if (!title) return;
    const { error } = await api.POST('/tasks', {
      body: {
        title,
        project_id: typeof filter === 'number' ? filter : null,
        status: 'todo',
      },
    });
    if (!error) {
      setQuickTitle('');
      void loadTasks(filter);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleteBusy(true);
    try {
      const { error } = await api.DELETE('/tasks/{task_id}', {
        params: { path: { task_id: pendingDelete.id } },
      });
      if (!error) void loadTasks(filter);
    } finally {
      setDeleteBusy(false);
      setPendingDelete(null);
    }
  };

  const composerProjectId = typeof filter === 'number' ? filter : null;
  const total = tasks?.length ?? 0;

  return (
    <div className="space-y-5">
      {/* Toolbar: project filter, view toggle, and the primary task actions. */}
      <div className="flex flex-wrap items-center gap-3 border-b border-line pb-3">
        <label className="flex items-center gap-2">
          <MonoLabel tone="faint">project</MonoLabel>
          <select
            aria-label="filter by project"
            value={filter === 'all' ? 'all' : String(filter)}
            onChange={(event) =>
              setFilter(event.target.value === 'all' ? 'all' : Number(event.target.value))
            }
            className="rounded-md border border-line bg-canvas px-2 py-1 text-sm text-cream outline-none focus:border-accent"
          >
            <option value="all">All projects</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-1">
          {(['board', 'list'] as ViewMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setView(mode)}
              aria-pressed={view === mode}
              className={[
                'mono-label rounded-md px-2 py-1 transition',
                view === mode ? 'bg-accent text-canvas' : 'border border-line hover:text-accent',
              ].join(' ')}
            >
              {mode}
            </button>
          ))}
        </div>

        {tasks ? <span className="mono-meta text-faint">{total} in view</span> : null}

        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" onClick={() => setPulling(true)}>
            Pull from research
          </Button>
          <Button variant="primary" onClick={() => setCreating(true)}>
            + New task
          </Button>
        </div>
      </div>

      {/* Fast inline add: a title plus return creates a To do task in the current project. */}
      <div className="flex items-center gap-2">
        <input
          value={quickTitle}
          onChange={(event) => setQuickTitle(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && quickTitle.trim()) void quickAdd();
          }}
          placeholder="Quick add a task, then press return"
          className={inputClass}
        />
        <Button variant="muted" onClick={() => void quickAdd()} disabled={!quickTitle.trim()}>
          add
        </Button>
      </div>

      {tasksError ? (
        <p className="text-sm text-muted">Tasks are unavailable. Check the Brain connection.</p>
      ) : tasks === null ? (
        <p className="text-sm text-muted">Loading tasks…</p>
      ) : total === 0 ? (
        <GlassCard className="border-electric">
          <MonoLabel tone="faint">no tasks yet</MonoLabel>
          <p className="mt-2 text-sm text-muted">
            {typeof filter === 'number'
              ? 'Nothing under this project yet. Quick add one above, or create one with New task.'
              : 'Add your first task above or with New task. Tasks also arrive from Research findings and from agent runs, and Reminders fold in here.'}
          </p>
        </GlassCard>
      ) : view === 'board' ? (
        <div className="flex gap-5 overflow-x-auto pb-2">
          {COLUMNS.map((column) => (
            <Column
              key={column.key}
              columnKey={column.key}
              label={STATUS_LABEL[column.key]}
              tasks={byStatus[column.key]}
              projectNameFor={projectNameFor}
              onMove={(task, status) => void move(task, status)}
              onEdit={(task) => setEditing(task)}
              onDelete={(task) => setPendingDelete(task)}
              onOpenRun={(runId) => setOpenRunId(runId)}
              onDropTask={moveById}
            />
          ))}
        </div>
      ) : (
        <ListView tasks={tasks} projectNameFor={projectNameFor} onEdit={(task) => setEditing(task)} />
      )}

      {/* New Task dialog. */}
      <Modal open={creating} title="new task" onClose={() => setCreating(false)}>
        <TaskForm
          initial={{ project_id: composerProjectId, status: 'todo', priority: 'med' }}
          projects={projects}
          showStatus
          submitLabel="Add task"
          onSubmit={createTask}
          onCancel={() => setCreating(false)}
        />
      </Modal>

      {/* Edit happens in a modal so the board stays in place behind it. */}
      <Modal open={editing !== null} title="edit task" onClose={() => setEditing(null)}>
        {editing ? (
          <TaskForm
            initial={{
              title: editing.title,
              detail: editing.detail ?? '',
              goal_for_agent: editing.goal_for_agent ?? '',
              project_id: editing.project_id,
              timeline: editing.timeline ?? '',
              priority: (editing.priority as Priority) ?? 'med',
              status: (columnFor(editing) ?? 'todo') as Status,
              due_date: editing.due_date ?? null,
            }}
            projects={projects}
            showStatus
            submitLabel="Save"
            onSubmit={(values) => saveTask(editing, values)}
            onCancel={() => setEditing(null)}
          />
        ) : null}
      </Modal>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete task"
        body="Delete this task? It is soft deleted and stays recoverable."
        confirmLabel="Delete"
        busy={deleteBusy}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />

      <ResearchPicker
        open={pulling}
        onClose={() => setPulling(false)}
        onPulled={() => void loadTasks(filter)}
      />

      <RunTimelineModal runId={openRunId} onClose={() => setOpenRunId(null)} />
    </div>
  );
}
