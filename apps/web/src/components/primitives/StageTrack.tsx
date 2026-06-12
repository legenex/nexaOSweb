import { Fragment } from 'react';

import { MonoLabel } from './MonoLabel';
import { StatusDot } from './StatusDot';
import type { DotState } from './StatusDot';

export interface TrackNode {
  label: string;
  state: DotState;
}

// The horizontal dotted track with labeled nodes. Reused for in card mini journeys and the
// Projects tail.
export function StageTrack({ nodes }: { nodes: TrackNode[] }) {
  return (
    <div className="flex items-center gap-1">
      {nodes.map((node, index) => (
        <Fragment key={node.label}>
          <div className="flex flex-col items-center gap-1">
            <StatusDot state={node.state} />
            <MonoLabel tone="faint" className="text-[0.55rem]">
              {node.label}
            </MonoLabel>
          </div>
          {index < nodes.length - 1 ? (
            <span
              aria-hidden
              className="mb-4 h-px w-6 border-t border-dotted border-line"
            />
          ) : null}
        </Fragment>
      ))}
    </div>
  );
}
