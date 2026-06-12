import { GlassCard, MonoLabel, Pill, StageTrack } from '../../components/primitives';
import type { TrackNode } from '../../components/primitives';
import { useFlow } from '../flow/FlowProvider';
import type { Project } from '../flow/FlowProvider';

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
  const { projects } = useFlow();

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
    <div className="grid gap-4 md:grid-cols-2">
      {projects.map((project: Project) => (
        <GlassCard key={project.id} className="border-electric">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-base font-semibold text-cream">{project.name}</h3>
            <Pill variant={project.stage === 'build' ? 'green' : 'accent'}>{project.stage}</Pill>
          </div>
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
        </GlassCard>
      ))}
    </div>
  );
}
