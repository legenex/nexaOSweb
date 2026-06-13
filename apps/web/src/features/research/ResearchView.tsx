import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { apiFetch } from '../../app/api';
import { api } from '../../app/client';
import { OverflowMenu } from '../../components/OverflowMenu';
import { Button, GlassCard, MonoLabel, Pill } from '../../components/primitives';
import { ConfirmDialog } from '../projects/workspace/ConfirmDialog';
import { FindingCard } from './FindingCard';
import type { FindingActionKey } from './FindingCard';
import { ResearchProjectDialog } from './ResearchProjectDialog';

type ResearchProject = Schemas['ResearchProjectRead'];
type BuildProject = Schemas['ProjectRead'];
type ResearchRun = Schemas['ResearchRunRead'];
type ResearchFinding = Schemas['ResearchFindingRead'];

function downloadMarkdown(filename: string, content: string): void {
  const blob = new Blob([content], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function RunCard({ run }: { run: ResearchRun }) {
  const [open, setOpen] = useState(false);
  const takeaways = run.key_takeaways ?? [];
  const suggestions = run.suggestions ?? [];
  return (
    <div className="rounded-md border border-line bg-surface/60">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left"
      >
        <span className="mono-meta text-muted">{new Date(run.created_at).toLocaleString()}</span>
        <span className="flex items-center gap-2">
          <Pill
            variant={
              run.status === 'completed' ? 'green' : run.status === 'failed' ? 'grey' : 'accent'
            }
          >
            {run.status}
          </Pill>
          <span className="mono-meta text-faint">{run.findings_count} findings</span>
        </span>
      </button>
      {open ? (
        <div className="space-y-3 border-t border-line px-3 py-3">
          {run.summary ? (
            <div>
              <MonoLabel tone="faint">synthesis</MonoLabel>
              <p className="mt-1 text-sm text-muted">{run.summary}</p>
            </div>
          ) : null}
          {run.analysis ? (
            <div>
              <MonoLabel tone="faint">analysis</MonoLabel>
              <p className="mt-1 text-sm text-muted">{run.analysis}</p>
            </div>
          ) : null}
          {takeaways.length > 0 ? (
            <div>
              <MonoLabel tone="faint">key takeaways</MonoLabel>
              <ul className="mt-1 list-disc pl-4 text-sm text-muted">
                {takeaways.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {suggestions.length > 0 ? (
            <div>
              <MonoLabel tone="faint">suggestions</MonoLabel>
              <ul className="mt-1 list-disc pl-4 text-sm text-muted">
                {suggestions.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function ResearchView() {
  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [buildProjects, setBuildProjects] = useState<BuildProject[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [runs, setRuns] = useState<ResearchRun[]>([]);
  const [findings, setFindings] = useState<ResearchFinding[]>([]);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [attachTarget, setAttachTarget] = useState<number | ''>('');

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ResearchProject | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ResearchProject | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [renaming, setRenaming] = useState<{ id: number; value: string } | null>(null);

  const selected = useMemo(
    () => projects.find((p) => p.id === selectedId) ?? null,
    [projects, selectedId],
  );
  const isAttached = selected?.research_target_id != null;
  const targetProject = useMemo(
    () => buildProjects.find((p) => p.id === selected?.research_target_id) ?? null,
    [buildProjects, selected],
  );

  const loadProjects = useCallback(async () => {
    const [research, builds] = await Promise.all([
      api.GET('/research/projects'),
      api.GET('/projects'),
    ]);
    setProjects((research.data as ResearchProject[]) ?? []);
    setBuildProjects((builds.data as BuildProject[]) ?? []);
  }, []);

  const loadDetail = useCallback(async (id: number) => {
    const [runsRes, findingsRes] = await Promise.all([
      api.GET('/research/{research_id}/runs', { params: { path: { research_id: id } } }),
      api.GET('/research/{research_id}/findings', { params: { path: { research_id: id } } }),
    ]);
    setRuns((runsRes.data as ResearchRun[]) ?? []);
    setFindings((findingsRes.data as ResearchFinding[]) ?? []);
  }, []);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  const select = useCallback(
    async (id: number) => {
      setSelectedId(id);
      setAttachTarget('');
      setRunError(null);
      await loadDetail(id);
    },
    [loadDetail],
  );

  const duplicate = useCallback(
    async (project: ResearchProject) => {
      await api.POST('/research/projects/{research_id}/duplicate', {
        params: { path: { research_id: project.id } },
      });
      await loadProjects();
    },
    [loadProjects],
  );

  const doDelete = useCallback(async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.DELETE('/research/projects/{research_id}', {
        params: { path: { research_id: deleteTarget.id } },
      });
      if (selectedId === deleteTarget.id) setSelectedId(null);
      setDeleteTarget(null);
      await loadProjects();
    } finally {
      setDeleting(false);
    }
  }, [deleteTarget, selectedId, loadProjects]);

  const renameProject = useCallback(async () => {
    if (!renaming) return;
    const next = renaming.value.trim();
    const target = projects.find((p) => p.id === renaming.id);
    if (next && target && next !== target.name) {
      await api.PATCH('/research/projects/{research_id}', {
        params: { path: { research_id: renaming.id } },
        body: { name: next },
      });
      await loadProjects();
    }
    setRenaming(null);
  }, [renaming, projects, loadProjects]);

  const runNow = useCallback(async () => {
    if (selectedId === null) return;
    setRunning(true);
    setRunError(null);
    try {
      const { error } = await api.POST('/research/{research_id}/runs', {
        params: { path: { research_id: selectedId } },
      });
      if (error) {
        const detail = (error as { detail?: string } | undefined)?.detail;
        setRunError(detail || 'The research run failed.');
        return;
      }
      await loadDetail(selectedId);
    } finally {
      setRunning(false);
    }
  }, [selectedId, loadDetail]);

  const attach = useCallback(async () => {
    if (selectedId === null || attachTarget === '') return;
    await api.POST('/research/{research_id}/attach', {
      params: { path: { research_id: selectedId } },
      body: { target_project_id: attachTarget },
    });
    await loadProjects();
  }, [selectedId, attachTarget, loadProjects]);

  const detach = useCallback(async () => {
    if (selectedId === null) return;
    await api.POST('/research/{research_id}/detach', {
      params: { path: { research_id: selectedId } },
    });
    await loadProjects();
  }, [selectedId, loadProjects]);

  const onAct = useCallback(
    async (action: FindingActionKey, finding: ResearchFinding): Promise<string> => {
      if (action === 'builder') {
        const form = new FormData();
        form.append('name', finding.title);
        form.append('body', finding.detail);
        form.append('source', 'research');
        const response = await apiFetch('/intake/capture', { method: 'POST', body: form });
        if (!response.ok) throw new Error('send to Project Builder failed');
        return 'Sent to Project Builder';
      }
      if (action === 'task') {
        const { error } = await api.POST('/research/findings/{finding_id}/to-task', {
          params: { path: { finding_id: finding.id } },
        });
        if (error) throw new Error('create task failed');
        if (selectedId !== null) await loadDetail(selectedId);
        return 'Task created';
      }
      if (action === 'knowledge') {
        const { error } = await api.POST('/research/findings/{finding_id}/to-knowledge', {
          params: { path: { finding_id: finding.id } },
        });
        if (error) throw new Error('save to Knowledge failed');
        if (selectedId !== null) await loadDetail(selectedId);
        return 'Saved to Knowledge';
      }
      const { error } = await api.POST('/research/findings/{finding_id}/to-update', {
        params: { path: { finding_id: finding.id } },
      });
      if (error) throw new Error('the research project is not attached to a build project');
      if (selectedId !== null) await loadDetail(selectedId);
      return action === 'brief' ? 'Project brief updated' : 'Added to project log';
    },
    [selectedId, loadDetail],
  );

  const exportRuns = useCallback(() => {
    if (!selected) return;
    const lines = [
      `# Research: ${selected.name}`,
      selected.topic ? `Topic: ${selected.topic}` : '',
      '',
      ...runs.flatMap((run) => [
        `## Run ${new Date(run.created_at).toLocaleString()} (${run.status})`,
        run.summary,
        run.analysis,
        ...(run.suggestions ?? []).map((s) => `- ${s}`),
        '',
      ]),
    ];
    downloadMarkdown(
      `research-${selected.slug}.md`,
      lines.filter((l) => l !== undefined).join('\n'),
    );
  }, [selected, runs]);

  // Group by the editable category label.
  const grouped = useMemo(() => {
    const map = new Map<string, ResearchProject[]>();
    for (const project of projects) {
      const cat = project.category || 'general';
      const list = map.get(cat) ?? [];
      list.push(project);
      map.set(cat, list);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [projects]);

  const attachOptions = buildProjects.filter((p) => p.id !== selectedId);

  return (
    <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
      <aside className="space-y-4">
        <div className="flex items-center justify-between">
          <MonoLabel tone="faint">research library</MonoLabel>
          <Button
            variant="outline"
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
          >
            Add
          </Button>
        </div>

        {projects.length === 0 ? (
          <p className="text-sm text-muted">No research projects yet. Add one to begin.</p>
        ) : (
          grouped.map(([category, items]) => (
            <div key={category}>
              <div className="mb-1">
                <span className="mono-label text-accent">{category}</span>
              </div>
              <div className="space-y-1">
                {items.map((project) => (
                  <div
                    key={project.id}
                    className={[
                      'flex items-center justify-between rounded-md px-2 transition',
                      project.id === selectedId ? 'bg-accent/15' : 'hover:bg-white/5',
                    ].join(' ')}
                  >
                    {renaming?.id === project.id ? (
                      <input
                        autoFocus
                        value={renaming.value}
                        onChange={(e) => setRenaming({ id: project.id, value: e.target.value })}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void renameProject();
                          if (e.key === 'Escape') setRenaming(null);
                        }}
                        onBlur={() => void renameProject()}
                        aria-label={`Rename ${project.name}`}
                        className="my-1 w-full rounded-md border border-line bg-canvas px-2 py-1 text-sm text-cream outline-none focus:border-accent"
                      />
                    ) : (
                      <button
                        type="button"
                        onClick={() => void select(project.id)}
                        className={[
                          'flex-1 truncate py-2 pl-1 text-left text-sm',
                          project.id === selectedId ? 'text-accent' : 'text-cream/85',
                        ].join(' ')}
                      >
                        {project.name}
                      </button>
                    )}
                    <OverflowMenu
                      label={`Actions for ${project.name}`}
                      items={[
                        {
                          label: 'Rename',
                          onClick: () => setRenaming({ id: project.id, value: project.name }),
                        },
                        {
                          label: 'Edit',
                          onClick: () => {
                            setEditing(project);
                            setDialogOpen(true);
                          },
                        },
                        { label: 'Duplicate', onClick: () => void duplicate(project) },
                        { label: 'Delete', danger: true, onClick: () => setDeleteTarget(project) },
                      ]}
                    />
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </aside>

      <section className="space-y-5">
        {selected === null ? (
          <GlassCard className="border-electric">
            <MonoLabel tone="faint">no research project selected</MonoLabel>
            <p className="mt-2 text-sm text-muted">Pick a project, or add one, to run research.</p>
          </GlassCard>
        ) : (
          <>
            <GlassCard className="border-electric">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="text-lg font-semibold text-cream">{selected.name}</h2>
                  {selected.topic ? (
                    <p className="mt-1 text-sm text-muted">{selected.topic}</p>
                  ) : null}
                  {selected.purpose ? (
                    <p className="mt-1 text-xs text-faint">{selected.purpose}</p>
                  ) : null}
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button onClick={() => void runNow()} disabled={running}>
                    {running ? 'running' : 'Run now'}
                  </Button>
                  <Button variant="outline" onClick={exportRuns} disabled={runs.length === 0}>
                    Export
                  </Button>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Pill variant="grey">{selected.depth}</Pill>
                <Pill variant="grey">{selected.lookback}d lookback</Pill>
                <Pill variant="grey">schedule {selected.schedule}</Pill>
              </div>

              {runError ? <p className="mt-3 text-sm text-danger">{runError}</p> : null}

              <div className="mt-4 border-t border-line pt-4">
                <MonoLabel tone="faint">attach to project</MonoLabel>
                {isAttached ? (
                  <div className="mt-2 flex items-center gap-3">
                    <span className="text-sm text-muted">
                      feeding{' '}
                      <span className="text-accent">{targetProject?.name ?? 'a project'}</span>
                    </span>
                    <Button variant="muted" onClick={() => void detach()}>
                      Detach
                    </Button>
                  </div>
                ) : (
                  <div className="mt-2 flex items-center gap-2">
                    <select
                      value={attachTarget}
                      onChange={(e) =>
                        setAttachTarget(e.target.value === '' ? '' : Number(e.target.value))
                      }
                      className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-cream"
                    >
                      <option value="">Select a build project</option>
                      {attachOptions.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                    <Button onClick={() => void attach()} disabled={attachTarget === ''}>
                      Attach
                    </Button>
                  </div>
                )}
              </div>
            </GlassCard>

            <div className="space-y-2">
              <MonoLabel tone="faint">run history</MonoLabel>
              {runs.length === 0 ? (
                <p className="text-sm text-muted">No runs yet. Run now to generate findings.</p>
              ) : (
                <div className="scroll-themed max-h-80 space-y-2 overflow-y-auto pr-1">
                  {runs.map((run) => (
                    <RunCard key={run.id} run={run} />
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-3">
              <MonoLabel tone="faint">findings</MonoLabel>
              {findings.length === 0 ? (
                <p className="text-sm text-muted">No findings yet.</p>
              ) : (
                findings.map((finding) => (
                  <FindingCard
                    key={finding.id}
                    finding={finding}
                    isAttached={isAttached}
                    onAct={onAct}
                  />
                ))
              )}
            </div>
          </>
        )}
      </section>

      <ResearchProjectDialog
        open={dialogOpen}
        initial={editing}
        onClose={() => setDialogOpen(false)}
        onSaved={() => void loadProjects()}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="delete research project"
        body={`Delete ${deleteTarget?.name ?? 'this project'}? This removes its runs and findings.`}
        confirmLabel="Delete"
        busy={deleting}
        onConfirm={() => void doDelete()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
