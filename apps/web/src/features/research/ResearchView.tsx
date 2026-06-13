import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { apiFetch } from '../../app/api';
import { api } from '../../app/client';
import { Button, GlassCard, MonoLabel, Pill } from '../../components/primitives';
import { RESEARCH_CATEGORIES, groupByCategory } from './categories';
import { FindingCard } from './FindingCard';
import type { FindingActionKey } from './FindingCard';

type Project = Schemas['ProjectRead'];
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

export function ResearchView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [runs, setRuns] = useState<ResearchRun[]>([]);
  const [findings, setFindings] = useState<ResearchFinding[]>([]);
  const [attachTarget, setAttachTarget] = useState<number | ''>('');
  const [running, setRunning] = useState(false);

  const selected = useMemo(
    () => projects.find((project) => project.id === selectedId) ?? null,
    [projects, selectedId],
  );
  const isAttached = selected?.research_target_id != null;
  const targetProject = useMemo(
    () => projects.find((project) => project.id === selected?.research_target_id) ?? null,
    [projects, selected],
  );

  const loadProjects = useCallback(async () => {
    const { data } = await api.GET('/projects');
    setProjects((data as Project[]) ?? []);
  }, []);

  const loadResearch = useCallback(async (researchId: number) => {
    const [runsRes, findingsRes] = await Promise.all([
      api.GET('/research/{research_id}/runs', { params: { path: { research_id: researchId } } }),
      api.GET('/research/{research_id}/findings', { params: { path: { research_id: researchId } } }),
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
      await loadResearch(id);
    },
    [loadResearch],
  );

  const runResearch = useCallback(async () => {
    if (selectedId === null) return;
    setRunning(true);
    try {
      await api.POST('/research/{research_id}/runs', {
        params: { path: { research_id: selectedId } },
      });
      await loadResearch(selectedId);
    } finally {
      setRunning(false);
    }
  }, [selectedId, loadResearch]);

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

  // One handler for the five finding actions. Returns the message the card shows.
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
        if (selectedId !== null) await loadResearch(selectedId);
        return 'Task created';
      }

      if (action === 'knowledge') {
        const { error } = await api.POST('/research/findings/{finding_id}/to-knowledge', {
          params: { path: { finding_id: finding.id } },
        });
        if (error) throw new Error('save to Knowledge failed');
        if (selectedId !== null) await loadResearch(selectedId);
        return 'Saved to Knowledge';
      }

      // add and brief both write the finding into the attached project's Update Log, which is
      // the project's running brief. The backend exposes one finding to project write today.
      const { error } = await api.POST('/research/findings/{finding_id}/to-update', {
        params: { path: { finding_id: finding.id } },
      });
      if (error) throw new Error('the research project is not attached to a build project');
      if (selectedId !== null) await loadResearch(selectedId);
      return action === 'brief' ? 'Project brief updated' : 'Added to project log';
    },
    [selectedId, loadResearch],
  );

  const exportFindings = useCallback(() => {
    if (!selected) return;
    const lines = [
      `# Research: ${selected.name}`,
      '',
      ...findings.flatMap((finding) => [
        `## ${finding.title}`,
        finding.detail || '',
        finding.url ? `Source: ${finding.url}` : '',
        '',
      ]),
    ];
    downloadMarkdown(`research-${selected.slug}.md`, lines.join('\n'));
  }, [selected, findings]);

  const groups = useMemo(() => groupByCategory(projects), [projects]);
  const latestRun = runs[0] ?? null;
  const attachOptions = projects.filter((project) => project.id !== selectedId);

  return (
    <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
      {/* Research library, grouped by category. */}
      <aside className="space-y-4">
        <MonoLabel tone="faint">research library</MonoLabel>
        {RESEARCH_CATEGORIES.map((category) => {
          const items = groups[category];
          if (items.length === 0) return null;
          return (
            <div key={category}>
              <div className="mono-label mb-1 text-accent">{category}</div>
              <div className="space-y-1">
                {items.map((project) => (
                  <button
                    key={project.id}
                    type="button"
                    onClick={() => void select(project.id)}
                    className={[
                      'block w-full truncate rounded-md px-3 py-2 text-left text-sm transition',
                      project.id === selectedId
                        ? 'bg-accent text-black'
                        : 'text-cream/85 hover:bg-white/5',
                    ].join(' ')}
                  >
                    {project.name}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
        {projects.length === 0 ? (
          <p className="text-sm text-muted">No projects yet to research.</p>
        ) : null}
      </aside>

      {/* Selected research project. */}
      <section className="space-y-5">
        {selected === null ? (
          <GlassCard className="border-electric">
            <MonoLabel tone="faint">no research project selected</MonoLabel>
            <p className="mt-2 text-sm text-muted">
              Pick a project from the library to run research and act on findings.
            </p>
          </GlassCard>
        ) : (
          <>
            <GlassCard className="border-electric">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold text-cream">{selected.name}</h2>
                <div className="flex gap-2">
                  <Button onClick={() => void runResearch()} disabled={running}>
                    {running ? 'running' : 'Run research'}
                  </Button>
                  <Button variant="outline" onClick={exportFindings} disabled={findings.length === 0}>
                    Export
                  </Button>
                </div>
              </div>

              {/* Attach to Project control. */}
              <div className="mt-4 border-t border-line pt-4">
                <MonoLabel tone="faint">attach to project</MonoLabel>
                {isAttached ? (
                  <div className="mt-2 flex items-center gap-3">
                    <span className="text-sm text-muted">
                      feeding <span className="text-accent">{targetProject?.name ?? 'a project'}</span>
                    </span>
                    <Button variant="muted" onClick={() => void detach()}>
                      Detach
                    </Button>
                  </div>
                ) : (
                  <div className="mt-2 flex items-center gap-2">
                    <select
                      value={attachTarget}
                      onChange={(event) =>
                        setAttachTarget(event.target.value === '' ? '' : Number(event.target.value))
                      }
                      className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-cream"
                    >
                      <option value="">Select a build project</option>
                      {attachOptions.map((project) => (
                        <option key={project.id} value={project.id}>
                          {project.name}
                        </option>
                      ))}
                    </select>
                    <Button onClick={() => void attach()} disabled={attachTarget === ''}>
                      Attach
                    </Button>
                  </div>
                )}
              </div>

              {/* Latest run synthesis. */}
              {latestRun ? (
                <div className="mt-4 border-t border-line pt-4">
                  <div className="flex items-center gap-2">
                    <MonoLabel tone="faint">synthesis</MonoLabel>
                    <Pill variant={latestRun.status === 'completed' ? 'green' : 'grey'}>
                      {latestRun.findings_count} findings
                    </Pill>
                  </div>
                  <p className="mt-2 text-sm text-muted">
                    {latestRun.summary || 'Run research to generate findings.'}
                  </p>
                </div>
              ) : null}
            </GlassCard>

            {/* Findings with actions. */}
            <div className="space-y-3">
              <MonoLabel tone="faint">findings</MonoLabel>
              {findings.length === 0 ? (
                <p className="text-sm text-muted">No findings yet. Run research to produce them.</p>
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

            {/* Run history. */}
            {runs.length > 0 ? (
              <div className="space-y-2">
                <MonoLabel tone="faint">runs</MonoLabel>
                {runs.map((run) => (
                  <div
                    key={run.id}
                    className="flex items-center justify-between rounded-md border border-line bg-surface/60 px-3 py-2"
                  >
                    <span className="mono-meta">run {run.id}</span>
                    <span className="mono-meta text-muted">
                      {run.status} · {run.findings_count} findings
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}
