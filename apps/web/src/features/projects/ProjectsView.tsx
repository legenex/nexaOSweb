import { useState } from 'react';

import { OverflowMenu } from '../../components/OverflowMenu';
import { Button, GlassCard, Modal, MonoLabel, Pill, StageTrack } from '../../components/primitives';
import type { TrackNode } from '../../components/primitives';
import { useFlow } from '../flow/FlowProvider';
import type { Project } from '../flow/FlowProvider';
import { ProjectWorkspace } from './workspace/ProjectWorkspace';
import { ConfirmDialog } from './workspace/ConfirmDialog';

// The project lifecycle stages shown on the tail track.
const LIFECYCLE = ['idea', 'process', 'clarify', 'approved', 'build', 'live'];

function trackFor(stage: string): TrackNode[] {
  const currentIndex = LIFECYCLE.indexOf(stage);
  return LIFECYCLE.map((name, index) => ({
    label: name,
    state:
      index < currentIndex
        ? 'done'
        : index === currentIndex
          ? stage === 'build'
            ? 'live'
            : 'current'
          : 'pending',
  }));
}

export function ProjectsView() {
  const { projects, renameProject, duplicateProject, deleteProject } = useFlow();
  const [openId, setOpenId] = useState<number | null>(null);
  // The project pending a rename (modal) or a delete (confirm), plus the rename draft.
  const [renameTarget, setRenameTarget] = useState<Project | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = openId !== null ? (projects.find((entry) => entry.id === openId) ?? null) : null;
  if (open) {
    return <ProjectWorkspace project={open} onBack={() => setOpenId(null)} />;
  }

  const startRename = (project: Project) => {
    setError(null);
    setRenameValue(project.name);
    setRenameTarget(project);
  };

  const submitRename = async () => {
    if (!renameTarget) return;
    const name = renameValue.trim();
    if (!name) {
      setError('Name cannot be empty.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await renameProject(renameTarget.id, name);
      setRenameTarget(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const runDuplicate = async (project: Project) => {
    setError(null);
    try {
      await duplicateProject(project.id);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setBusy(true);
    setError(null);
    try {
      await deleteProject(deleteTarget.id);
      setDeleteTarget(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (projects.length === 0) {
    return (
      <section className="border-electric rounded-glass border border-line bg-surface/60 p-6">
        <MonoLabel tone="faint">no projects yet</MonoLabel>
        <p className="mt-2 text-sm text-muted">
          Run a project shaped item through Flow and approve it to see it here.
        </p>
      </section>
    );
  }

  return (
    <>
      {error ? <p className="mb-3 text-sm text-danger">{error}</p> : null}
      <div className="grid gap-4 md:grid-cols-2">
        {projects.map((project: Project) => (
          <GlassCard key={project.id} className="border-electric">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-base font-semibold text-cream">{project.name}</h3>
              <div className="flex items-center gap-1">
                <Pill variant="solid">{project.mode}</Pill>
                <Pill variant={project.stage === 'build' ? 'green' : 'accent'}>
                  {project.stage}
                </Pill>
                <OverflowMenu
                  label={`Actions for ${project.name}`}
                  items={[
                    { label: 'Rename', onClick: () => startRename(project) },
                    { label: 'Duplicate', onClick: () => void runDuplicate(project) },
                    {
                      label: 'Delete',
                      danger: true,
                      onClick: () => {
                        setError(null);
                        setDeleteTarget(project);
                      },
                    },
                  ]}
                />
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpenId(project.id)}
              className="block w-full text-left"
            >
              <MonoLabel tone="faint" className="mb-3 block">
                {project.slug}
              </MonoLabel>
              <StageTrack nodes={trackFor(project.stage)} />
              {project.build_destination ? (
                <p className="mt-3 text-sm">
                  <span className="text-muted">build </span>
                  <span className="text-accent">{project.build_destination}</span>
                </p>
              ) : null}
              <p className="mt-3">
                <MonoLabel tone="accent">open workspace →</MonoLabel>
              </p>
            </button>
          </GlassCard>
        ))}
      </div>

      <Modal
        open={renameTarget !== null}
        title="Rename project"
        onClose={() => (busy ? undefined : setRenameTarget(null))}
      >
        <label className="mb-2 block text-sm text-muted" htmlFor="project-rename">
          Project name
        </label>
        <input
          id="project-rename"
          type="text"
          value={renameValue}
          onChange={(event) => setRenameValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') void submitRename();
          }}
          autoFocus
          className="mb-4 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-cream outline-none focus:border-accent"
        />
        <div className="flex justify-end gap-2">
          <Button variant="muted" onClick={() => setRenameTarget(null)} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void submitRename()} disabled={busy}>
            {busy ? 'Working' : 'Save'}
          </Button>
        </div>
      </Modal>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete project"
        body={
          deleteTarget
            ? `Delete "${deleteTarget.name}"? It is removed from your projects but kept recoverable.`
            : ''
        }
        confirmLabel="Delete"
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleteTarget(null)}
        busy={busy}
      />
    </>
  );
}
