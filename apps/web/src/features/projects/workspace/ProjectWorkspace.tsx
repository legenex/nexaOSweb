import { useState } from 'react';

import { MonoLabel, Pill } from '../../../components/primitives';
import type { Project } from '../../flow/FlowProvider';
import { AiEditorTab } from './AiEditorTab';
import { BuildLogTab } from './BuildLogTab';
import { FilesTab } from './FilesTab';
import { OverviewTab } from './OverviewTab';
import { PreviewTab } from './PreviewTab';
import { RuntimeTab } from './RuntimeTab';
import { UpdateLogsTab } from './UpdateLogsTab';

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'preview', label: 'Preview Window' },
  { key: 'files', label: 'Files' },
  { key: 'runtime', label: 'Agent Timeline' },
  { key: 'build-log', label: 'Build Log' },
  { key: 'update-logs', label: 'Update Logs' },
  { key: 'ai-editor', label: 'AI Editor' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

// The per project workspace. A header with the project identity and a tab strip, then the
// active tab. Each tab reads live data from the Brain project endpoints.
export function ProjectWorkspace({ project, onBack }: { project: Project; onBack: () => void }) {
  const [tab, setTab] = useState<TabKey>('overview');
  // Bumped when the AI Editor applies or rolls back, so the Build Log reloads on next view.
  const [buildLogVersion, setBuildLogVersion] = useState(0);

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          className="mono-label rounded-md border border-line px-3 py-1 hover:text-accent"
        >
          ← projects
        </button>
        <h2 className="text-lg font-semibold text-cream">{project.name}</h2>
        <Pill variant="solid">{project.mode}</Pill>
        <Pill variant={project.stage === 'build' || project.stage === 'live' ? 'green' : 'accent'}>
          {project.stage}
        </Pill>
        <MonoLabel tone="faint">{project.slug}</MonoLabel>
      </div>

      <div
        role="tablist"
        aria-label="Project workspace tabs"
        className="flex flex-wrap gap-1 border-b border-line"
      >
        {TABS.map((entry) => (
          <button
            key={entry.key}
            role="tab"
            aria-selected={tab === entry.key}
            onClick={() => setTab(entry.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm transition ${
              tab === entry.key
                ? 'border-accent text-accent'
                : 'border-transparent text-muted hover:text-cream'
            }`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <div>
        {tab === 'overview' ? <OverviewTab projectId={project.id} /> : null}
        {tab === 'preview' ? <PreviewTab projectId={project.id} /> : null}
        {tab === 'files' ? <FilesTab projectId={project.id} /> : null}
        {tab === 'runtime' ? <RuntimeTab projectId={project.id} /> : null}
        {tab === 'build-log' ? <BuildLogTab key={buildLogVersion} projectId={project.id} /> : null}
        {tab === 'update-logs' ? <UpdateLogsTab projectId={project.id} /> : null}
        {tab === 'ai-editor' ? (
          <AiEditorTab
            projectId={project.id}
            onChange={() => setBuildLogVersion((value) => value + 1)}
          />
        ) : null}
      </div>
    </section>
  );
}
