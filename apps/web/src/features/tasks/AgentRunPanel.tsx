import { useCallback, useEffect, useRef, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { LEVEL_META, normalizeLevel, useProjectAutonomy } from '../../components/autonomy';
import { Button, MonoLabel, Pill, StatusDot } from '../../components/primitives';
import type { DotState } from '../../components/primitives';

type Task = Schemas['TaskRead'];
type AgentRun = Schemas['AgentRunDetail'];

// The autonomy gate decision recorded on a run (see services/brain/app/autonomy.py): the effective
// level, whether it auto advanced past the gate, and the categories and reasons behind any
// escalation. Read defensively from the run's loosely typed autonomy dict.
interface AutonomyDecision {
  effective_level?: string;
  auto_advance?: boolean;
  is_red?: boolean;
  categories?: string[];
  reasons?: string[];
}

function readAutonomy(run: AgentRun): AutonomyDecision | null {
  const raw = run.autonomy;
  if (!raw || typeof raw !== 'object') return null;
  return raw as AutonomyDecision;
}

// The build run lifecycle, as the panel reads it. status is the runtime roll up; phase is the
// build marker the engine sets. running covers planned and executing, gate is awaiting review.
const ACTIVE_STATUSES = new Set(['planned', 'executing', 'waiting_approval', 'blocked']);
const RUNNING_STATUSES = new Set(['planned', 'executing', 'blocked']);

function isAwaitingReview(run: AgentRun): boolean {
  return run.status === 'waiting_approval' && run.gate_step_id != null;
}

function phaseLabel(run: AgentRun): { text: string; dot: DotState } {
  if (run.status === 'waiting_approval') return { text: 'awaiting review', dot: 'gate' };
  if (RUNNING_STATUSES.has(run.status)) return { text: 'running', dot: 'live' };
  switch (run.phase) {
    case 'merged':
      return { text: 'merged', dot: 'done' };
    case 'rejected':
      return { text: 'rejected', dot: 'warn' };
    case 'cancelled':
      return { text: 'cancelled', dot: 'warn' };
    case 'failed':
      return { text: 'failed', dot: 'error' };
    default:
      return { text: run.status, dot: 'pending' };
  }
}

const preClass =
  'mt-2 max-h-72 overflow-auto rounded-md border border-line bg-canvas p-3 font-mono text-[0.72rem] leading-relaxed text-cream whitespace-pre-wrap';

// Surface the autonomy gate decision so a gated or auto merged run is explainable: the effective
// level with its color, whether it auto advanced, and the categories and reasons behind any gate.
function AutonomyDecisionPanel({ decision }: { decision: AutonomyDecision }) {
  const level = normalizeLevel(decision.effective_level);
  const meta = LEVEL_META[level];
  const autoAdvanced = decision.auto_advance === true;
  return (
    <div className="mt-3">
      <MonoLabel tone="faint">autonomy decision</MonoLabel>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5">
          <StatusDot state={meta.dot} label={`${meta.label} autonomy`} />
          <span className="mono-meta text-muted">{meta.label}</span>
        </span>
        <Pill variant={autoAdvanced ? 'green' : 'grey'}>
          {autoAdvanced ? 'auto advanced' : 'gated for review'}
        </Pill>
      </div>
      {decision.categories && decision.categories.length > 0 ? (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <MonoLabel tone="faint">categories</MonoLabel>
          {decision.categories.map((category) => (
            <Pill key={category} variant="grey">
              {category}
            </Pill>
          ))}
        </div>
      ) : null}
      {decision.reasons && decision.reasons.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {decision.reasons.map((reason) => (
            <li key={reason} className="mono-meta text-faint">
              {reason}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

// The Send to agent control plus the run review panel for one task. It owns the full loop: start a
// run, poll its live status while it works, and once it parks at the human gate show the reasoning,
// the diff, and the transcript with Approve, Reject, and Cancel. The provider key never appears
// here: the panel only ever sees the diff and transcript the Brain returns.
export function AgentRunPanel({ task, onChanged }: { task: Task; onChanged: () => void }) {
  const [run, setRun] = useState<AgentRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTranscript, setShowTranscript] = useState(false);
  const pollRef = useRef<number | null>(null);

  const hasProject = task.project_id != null;
  // The project kill switch gates new runs: while engaged, Send to agent is disabled with a reason.
  const projectAutonomy = useProjectAutonomy(task.project_id);
  const killEngaged = projectAutonomy.state?.kill_switch_engaged ?? false;

  const loadRun = useCallback(async (runId: number): Promise<AgentRun | null> => {
    const { data, error: err } = await api.GET('/agents/runs/{run_id}', {
      params: { path: { run_id: runId } },
    });
    if (err || !data) return null;
    return data as AgentRun;
  }, []);

  // Load an existing build run when the task already links one (a run started earlier this session
  // or surfaced from the board). A task whose run is not a build run simply returns nothing.
  useEffect(() => {
    let cancelled = false;
    if (task.run_id == null) {
      setRun(null);
      return;
    }
    void loadRun(task.run_id).then((loaded) => {
      if (!cancelled) setRun(loaded);
    });
    return () => {
      cancelled = true;
    };
  }, [task.run_id, loadRun]);

  // Poll while the run is still working (running, not yet at the gate), so the status streams live.
  useEffect(() => {
    if (pollRef.current != null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (run == null || !RUNNING_STATUSES.has(run.status)) return;
    pollRef.current = window.setInterval(async () => {
      const next = await loadRun(run.id);
      if (next) setRun(next);
    }, 1500);
    return () => {
      if (pollRef.current != null) window.clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [run, loadRun]);

  const start = async () => {
    if (!hasProject) return;
    setBusy(true);
    setError(null);
    try {
      const { data, error: err, response } = await api.POST('/agents/runs', {
        body: { task_id: task.id },
      });
      if (err || !data) {
        if (response?.status === 503) {
          setError('The claude-code backend is not available in this environment.');
        } else {
          setError((err as { detail?: string } | undefined)?.detail ?? 'Could not start the run.');
        }
        return;
      }
      setRun(data as AgentRun);
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const act = async (verb: 'approve' | 'reject' | 'cancel') => {
    if (run == null) return;
    const params = { params: { path: { run_id: run.id } } };
    setBusy(true);
    setError(null);
    try {
      const result =
        verb === 'approve'
          ? await api.POST('/agents/runs/{run_id}/approve', params)
          : verb === 'reject'
            ? await api.POST('/agents/runs/{run_id}/reject', params)
            : await api.POST('/agents/runs/{run_id}/cancel', params);
      const { data, error: err } = result;
      if (err || !data) {
        setError((err as { detail?: string } | undefined)?.detail ?? `Could not ${verb} the run.`);
        return;
      }
      setRun(data as AgentRun);
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  // No run yet: the Send to agent control. A task needs a project (the worktree and merge target).
  if (run == null) {
    return (
      <div className="border-t border-line pt-4">
        <MonoLabel tone="faint">agent build</MonoLabel>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            onClick={() => void start()}
            disabled={busy || !hasProject || killEngaged}
          >
            {busy ? 'starting' : 'Send to agent'}
          </Button>
          {!hasProject ? (
            <span className="mono-meta text-faint">link a project first</span>
          ) : killEngaged ? (
            <span className="mono-meta text-danger">
              kill switch engaged, release it to send new runs
            </span>
          ) : (
            <span className="mono-meta text-faint">build this task in an isolated worktree</span>
          )}
        </div>
        {error ? <p className="mt-2 mono-meta text-danger">{error}</p> : null}
      </div>
    );
  }

  const { text, dot } = phaseLabel(run);
  const active = ACTIVE_STATUSES.has(run.status);
  const decision = readAutonomy(run);

  return (
    <div className="border-t border-line pt-4">
      <div className="flex items-center justify-between">
        <MonoLabel tone="faint">agent build</MonoLabel>
        <span className="inline-flex items-center gap-2">
          <StatusDot state={dot} label={text} />
          <span className="mono-meta text-muted">{text}</span>
          {run.backend ? <Pill variant="grey">{run.backend}</Pill> : null}
        </span>
      </div>

      {RUNNING_STATUSES.has(run.status) ? (
        <p className="mt-2 mono-meta text-faint">The agent is working in the isolated worktree…</p>
      ) : null}

      {decision ? <AutonomyDecisionPanel decision={decision} /> : null}

      {run.reasoning_summary ? (
        <div className="mt-3">
          <MonoLabel tone="faint">reasoning</MonoLabel>
          <p className="mt-1 whitespace-pre-wrap text-sm text-cream">{run.reasoning_summary}</p>
        </div>
      ) : null}

      {run.files_changed.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <MonoLabel tone="faint">files</MonoLabel>
          {run.files_changed.map((file) => (
            <Pill key={file} variant="accent">
              {file}
            </Pill>
          ))}
        </div>
      ) : null}

      {run.diff ? (
        <div className="mt-3">
          <div className="flex items-center justify-between">
            <MonoLabel tone="faint">diff</MonoLabel>
            {run.diff_shortstat ? (
              <span className="mono-meta text-faint">{run.diff_shortstat}</span>
            ) : null}
          </div>
          <pre className={preClass}>{run.diff}</pre>
          {run.diff_capped ? (
            <p className="mt-1 mono-meta text-faint">diff truncated for display</p>
          ) : null}
        </div>
      ) : null}

      {run.transcript ? (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowTranscript((v) => !v)}
            className="mono-label text-faint hover:text-cream"
          >
            {showTranscript ? 'hide transcript' : 'show transcript'}
          </button>
          {showTranscript ? <pre className={preClass}>{run.transcript}</pre> : null}
        </div>
      ) : null}

      {error ? <p className="mt-2 mono-meta text-danger">{error}</p> : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {isAwaitingReview(run) ? (
          <>
            <Button variant="primary" onClick={() => void act('approve')} disabled={busy}>
              {busy ? 'working' : 'Approve'}
            </Button>
            <Button variant="outline" onClick={() => void act('reject')} disabled={busy}>
              Reject
            </Button>
          </>
        ) : null}
        {active ? (
          <Button variant="muted" onClick={() => void act('cancel')} disabled={busy}>
            Cancel
          </Button>
        ) : null}
      </div>
    </div>
  );
}
