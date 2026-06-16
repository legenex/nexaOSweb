import { useRef } from 'react';
import type { ReactNode } from 'react';

import { HolographicSphere } from '../../components/HolographicSphere';
import { ProjectAutonomyBar } from '../../components/autonomy';
import { GlassCard, MonoLabel, Pill, StatusDot } from '../../components/primitives';
import type { DotState } from '../../components/primitives';
import { CaptureCard } from './cards/CaptureCard';
import { ClarifyCard } from './cards/ClarifyCard';
import { ClassifyCard } from './cards/ClassifyCard';
import { ExecuteCard } from './cards/ExecuteCard';
import { GateCard } from './cards/GateCard';
import { ProcessCard } from './cards/ProcessCard';
import { RouteCard } from './cards/RouteCard';
import { ConnectorLayer } from './ConnectorLayer';
import { useFlow } from './FlowProvider';
import type { FlowItem } from './FlowProvider';
import { currentStageIndex, STAGES } from './stages';

function PlaceholderCard({ stageLabel }: { stageLabel: string }) {
  return (
    <GlassCard>
      <div className="mb-3 flex items-center justify-between">
        <MonoLabel tone="accent">{stageLabel}</MonoLabel>
      </div>
      <p className="text-sm text-muted">Wired in a later prompt.</p>
    </GlassCard>
  );
}

function renderStageCard(stageKey: string, stageLabel: string, _selected: FlowItem | null): ReactNode {
  switch (stageKey) {
    case 'capture':
      return <CaptureCard />;
    case 'classify':
      return <ClassifyCard />;
    case 'route':
      return <RouteCard />;
    case 'process':
      return <ProcessCard />;
    case 'clarify':
      return <ClarifyCard />;
    case 'gate':
      return <GateCard />;
    case 'execute':
      return <ExecuteCard />;
    default:
      return <PlaceholderCard stageLabel={stageLabel} />;
  }
}

function RunsRail() {
  const { items, selectedId, select } = useFlow();
  if (items.length === 0) {
    return <MonoLabel tone="faint">no runs yet, capture an idea to begin</MonoLabel>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => {
        const active = item.id === selectedId;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => void select(item.id)}
            className={[
              'rounded-lg border px-3 py-1.5 text-left text-xs transition',
              active ? 'border-accent bg-accent/10 text-cream' : 'border-line text-muted hover:text-cream',
            ].join(' ')}
          >
            <span className="block max-w-[180px] truncate">{item.name}</span>
            <span className="mono-meta">{item.status}</span>
          </button>
        );
      })}
    </div>
  );
}

export function FlowPanorama() {
  const containerRef = useRef<HTMLDivElement>(null);
  const cardsRef = useRef<(HTMLDivElement | null)[]>([]);
  const { selected } = useFlow();
  const activeIndex = currentStageIndex(selected);

  return (
    <div className="space-y-5">
      {selected?.project_id != null ? (
        <div className="rounded-glass border border-line bg-surface/50 p-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <MonoLabel tone="accent">project builder</MonoLabel>
            <MonoLabel tone="faint">{selected.name}</MonoLabel>
          </div>
          <ProjectAutonomyBar projectId={selected.project_id} variant="header" />
        </div>
      ) : null}

      <div className="rounded-glass border border-line bg-surface/50 p-3">
        <MonoLabel tone="faint" className="mb-2 block">
          runs
        </MonoLabel>
        <RunsRail />
      </div>

      <div ref={containerRef} className="relative min-h-[520px]">
        <HolographicSphere />
        <ConnectorLayer container={containerRef} cards={cardsRef} activeIndex={activeIndex} />

        <div
          data-deck
          role="list"
          aria-label="Flow Builder pipeline stages"
          // Right and vertical padding so the last stage (Execute) and the active stage glow are
          // never clipped, and horizontal scroll reaches the final card.
          className="scroll-themed relative z-10 flex gap-7 overflow-x-auto px-1 pb-6 pr-10 pt-2"
        >
          {STAGES.map((stage, index) => {
            const isActive = index === activeIndex;
            const dot: DotState = isActive
              ? 'current'
              : selected && stageStateFor(stage.key, selected)
                ? stageStateFor(stage.key, selected)!
                : stage.dot;
            const terminalRoute = Boolean(selected?.route && selected.route !== 'project');
            const dimmed =
              terminalRoute && ['process', 'clarify', 'gate', 'execute'].includes(stage.key);
            return (
              <div
                key={stage.key}
                role="listitem"
                aria-label={`Stage ${stage.number}, ${stage.title}`}
                ref={(element) => {
                  cardsRef.current[index] = element;
                }}
                className={['w-[280px] shrink-0 transition', dimmed ? 'opacity-40' : ''].join(' ')}
              >
                <div className="mb-3 flex items-center gap-2">
                  <MonoLabel tone="accent">stage {stage.number}</MonoLabel>
                  <StatusDot state={dot} label={`${stage.title} ${dot}`} />
                </div>
                <h2 className="mb-1 text-[21px] font-semibold text-cream">{stage.title}</h2>
                <MonoLabel tone="faint" className="mb-3 block">
                  {stage.sublabel}
                </MonoLabel>
                {/* The electric current rings only the active stage's card, not the whole column. */}
                <div className={isActive ? 'relative rounded-glass border-electric border-electric-on' : ''}>
                  {renderStageCard(stage.key, stage.headerLabel, selected)}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {selected ? (
        <div className="flex items-center gap-2">
          <Pill variant="accent">{selected.route ?? 'unrouted'}</Pill>
          <MonoLabel tone="faint">selected run {selected.id}</MonoLabel>
        </div>
      ) : null}
    </div>
  );
}

// Maps a stage to a status dot based on the selected run, falling back to the static state.
function stageStateFor(stageKey: string, item: FlowItem): DotState | null {
  switch (stageKey) {
    case 'capture':
      return 'done';
    case 'classify':
      return item.classification ? 'done' : 'pending';
    case 'route':
      return item.route ? 'done' : 'pending';
    case 'process':
      return item.plan_available ? 'done' : 'pending';
    case 'clarify':
      return item.preview_available ? 'done' : 'pending';
    case 'gate':
      return item.gate_state === 'approved' ? 'done' : 'gate';
    case 'execute':
      return item.project_stage === 'build' ? 'live' : 'pending';
    default:
      return null;
  }
}
