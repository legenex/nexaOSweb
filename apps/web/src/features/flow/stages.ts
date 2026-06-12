import type { DotState } from '../../components/primitives';

export interface StageDef {
  key: string;
  number: string;
  title: string;
  sublabel: string;
  dot: DotState;
  headerLabel: string;
}

// The seven stages, left to right. State here is a static placeholder until the nodes are
// wired to data in W3 through W6.
export const STAGES: StageDef[] = [
  { key: 'capture', number: '01', title: 'Capture', sublabel: './nexa_projects/<slug>/', dot: 'done', headerLabel: 'intake' },
  { key: 'classify', number: '02', title: 'Classify', sublabel: 'inbox-classifier', dot: 'done', headerLabel: 'classify verdict' },
  { key: 'route', number: '03', title: 'Route', sublabel: 'eight workflows', dot: 'current', headerLabel: 'route' },
  { key: 'process', number: '04', title: 'Process', sublabel: './nexa_projects/<slug>/', dot: 'pending', headerLabel: 'project plan' },
  { key: 'clarify', number: '05', title: 'Clarify', sublabel: 'gap questions', dot: 'pending', headerLabel: 'clarify' },
  { key: 'gate', number: '06', title: 'Human Gate', sublabel: 'approve or send back', dot: 'gate', headerLabel: 'gate' },
  { key: 'execute', number: '07', title: 'Execute', sublabel: 'promote to builder', dot: 'pending', headerLabel: 'execute' },
];

// The index of the stage the run is currently crossing, for the brighter connector segment.
export const ACTIVE_INDEX = 2;
