import { useRef } from 'react';

import { HolographicSphere } from '../../components/HolographicSphere';
import { GlassCard, MonoLabel, StatusDot } from '../../components/primitives';
import { ConnectorLayer } from './ConnectorLayer';
import { ACTIVE_INDEX, STAGES } from './stages';

// The Flow route: a horizontal deck of the seven stage cards over the holographic backdrop,
// with the connector wires drawn behind the cards. Static placeholders, wired in W3 to W6.
export function FlowPanorama() {
  const containerRef = useRef<HTMLDivElement>(null);
  const cardsRef = useRef<(HTMLDivElement | null)[]>([]);

  return (
    <div ref={containerRef} className="relative min-h-[520px]">
      <HolographicSphere />
      <ConnectorLayer container={containerRef} cards={cardsRef} activeIndex={ACTIVE_INDEX} />

      <div
        data-deck
        className="relative z-10 flex gap-7 overflow-x-auto pb-6"
        style={{ scrollbarWidth: 'thin' }}
      >
        {STAGES.map((stage, index) => (
          <div
            key={stage.key}
            ref={(element) => {
              cardsRef.current[index] = element;
            }}
            className="w-[280px] shrink-0"
          >
            <div className="mb-3 flex items-center gap-2">
              <MonoLabel tone="accent">stage {stage.number}</MonoLabel>
              <StatusDot state={stage.dot} label={`${stage.title} ${stage.dot}`} />
            </div>
            <h2 className="mb-1 text-[21px] font-semibold text-cream">{stage.title}</h2>
            <MonoLabel tone="faint" className="mb-3 block">
              {stage.sublabel}
            </MonoLabel>

            <GlassCard active={index === ACTIVE_INDEX}>
              <div className="mb-3 flex items-center justify-between">
                <MonoLabel tone="accent">{stage.headerLabel}</MonoLabel>
                <MonoLabel tone="faint">stage {stage.number}</MonoLabel>
              </div>
              <p className="text-sm text-muted">
                Static placeholder. This node is wired to data in a later prompt.
              </p>
            </GlassCard>
          </div>
        ))}
      </div>
    </div>
  );
}
