import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { Button, GlassCard, Modal, MonoLabel, Pill } from '../../components/primitives';
import { OverflowMenu } from '../../components/OverflowMenu';
import { ConfirmDialog } from '../projects/workspace/ConfirmDialog';

type Task = Schemas['TaskRead'];
type Project = Schemas['ProjectRead'];

// The Hermes board columns, in order. The Brain validates this set. agent_working is also
// surfaced automatically for a task whose run is live; a legacy blocked task folds into Doing.
type Status = 'todo' | 'doing' | 'agent_working' | 'review' | 'done';

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

// 'all' is the cross project view; a number scopes the board to one project.
type ProjectFilter = number | 'all';

// --- composer -------------------------------------------------------------------------------

function Composer({
  projectId,
  onCreated,
}: {
  projectId: number | null;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState('');
  const [detail, setDetail] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!title.trim()) return;
    setBusy(true);
    try {
      const { error } = await api.POST('/tasks', {
        body: {
          title: title.trim(),
          detail: detail.trim() || null,
          project_id: projectId,
        },
      });
      if (!error) {
        setTitle('');
        setDetail('');
        onCreated();
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <GlassCard className="border-electric">
      <MonoLabel tone="accent">new task</MonoLabel>
      <input
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && title.trim()) void submit();
        }}
        placeholder="What needs doing?"
        className={`mt-2 ${inputClass}`}
      />
      <textarea
        value={detail}
        onChange={(event) => setDetail(event.target.value)}
        rows={2}
        placeholder="detail (optional)"
        className={`mt-2 resize-none ${inputClass}`}
      />
      <div className="mt-3">
        <Button variant="primary" onClick={() => void submit()} disabled={!title.trim() || busy}>
          {busy ? 'saving' : 'Add task'}
        </Button>
      </div>
    </GlassCard>
  );
}

// --- editor ---------------------------------------------------------------------------------

function TaskEditor({
  task,
  onSaved,
  onCancel,
}: {
  task: Task;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(task.title);
  const [detail, setDetail] = useState(task.detail ?? '');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!title.trim()) return;
    setBusy(true);
    try {
      const { error } = await api.PATCH('/tasks/{task_id}', {
        params: { path: { task_id: task.id } },
        body: { title: title.trim(), detail: detail.trim() || null },
      });
      if (!error) onSaved();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <input
        value={title}
        autoFocus
        onChange={(event) => setTitle(event.target.value)}
        className={inputClass}
      />
      <textarea
        value={detail}
        onChange={(event) => setDetail(event.target.value)}
        rows={2}
        placeholder="detail"
        className={`resize-none ${inputClass}`}
      />
      <div className="flex gap-2">
        <Button variant="primary" onClick={() => void save()} disabled={busy || !title.trim()}>
          save
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

// --- task card ------------------------------------------------------------------------------

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

// --- view -----------------------------------------------------------------------------------

export function TasksView() {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [tasksError, setTasksError] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [filter, setFilter] = useState<ProjectFilter>('all');

  const [editing, setEditing] = useState<Task | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Task | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [openRunId, setOpenRunId] = useState<number | null>(null);

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

  const move = async (task: Task, status: Status) => {
    const { error } = await api.PATCH('/tasks/{task_id}', {
      params: { path: { task_id: task.id } },
      body: { status },
    });
    if (!error) void loadTasks(filter);
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

  // A drop onto a column moves the dragged task to that status.
  const moveById = (taskId: number, status: Status) => {
    const task = (tasks ?? []).find((entry) => entry.id === taskId);
    if (task) void move(task, status);
  };

  const composerProjectId = typeof filter === 'number' ? filter : null;
  const total = tasks?.length ?? 0;

  return (
    <div className="space-y-5">
      {/* Project filter. 'all' is the cross project board; a project scopes the board and seeds
          the composer so a new task lands in the filtered project. */}
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
        {tasks ? <span className="mono-meta text-faint">{total} in view</span> : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-4">
          {tasksError ? (
            <p className="text-sm text-muted">
              Tasks are unavailable. Check the Brain connection.
            </p>
          ) : tasks === null ? (
            <p className="text-sm text-muted">Loading tasks…</p>
          ) : total === 0 ? (
            <GlassCard className="border-electric">
              <MonoLabel tone="faint">no tasks yet</MonoLabel>
              <p className="mt-2 text-sm text-muted">
                {typeof filter === 'number'
                  ? 'Nothing under this project yet. Add a task on the right, or move one here from another project.'
                  : 'Add your first task on the right. Tasks also arrive from Research findings and from agent runs, and Reminders fold in here.'}
              </p>
            </GlassCard>
          ) : (
            // The status board: a column per status, scrolling horizontally when narrow.
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
          )}
        </div>

        <aside>
          <Composer projectId={composerProjectId} onCreated={() => void loadTasks(filter)} />
        </aside>
      </div>

      {/* Edit happens in a modal so the board stays in place behind it. */}
      <Modal open={editing !== null} title="edit task" onClose={() => setEditing(null)}>
        {editing ? (
          <TaskEditor
            task={editing}
            onSaved={() => {
              setEditing(null);
              void loadTasks(filter);
            }}
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

      <RunTimelineModal runId={openRunId} onClose={() => setOpenRunId(null)} />
    </div>
  );
}
