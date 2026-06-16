import type { DotState } from '../primitives';

// The three settings of the autonomy dial, ordered from most to least autonomous, matching the
// Brain (see services/brain/app/autonomy.py): green runs unattended, yellow pauses at the human
// gate, red never auto runs.
export type AutonomyLevel = 'green' | 'yellow' | 'red';

export const AUTONOMY_LEVELS: AutonomyLevel[] = ['green', 'yellow', 'red'];

export interface LevelMeta {
  key: AutonomyLevel;
  label: string;
  // The status dot state carries the level color from the CSS variables: green (status green),
  // gold (gate gold), danger (danger red). Orange stays the only brand accent, never a level color.
  dot: DotState;
  help: string;
  // Tailwind class sets resolving to the same CSS variables. Written as full literal strings so the
  // JIT compiler keeps them; the selected option wears the level color, the rest stay neutral.
  selected: string;
  swatch: string;
}

export const LEVEL_META: Record<AutonomyLevel, LevelMeta> = {
  green: {
    key: 'green',
    label: 'Green',
    dot: 'live',
    help: 'Runs unattended start to finish and auto merges.',
    selected: 'border-status-green bg-status-green/10 text-status-green',
    swatch: 'bg-status-green',
  },
  yellow: {
    key: 'yellow',
    label: 'Yellow',
    dot: 'gate',
    help: 'Pauses at the human gate and waits for approval.',
    selected: 'border-gate-gold bg-gate-gold/10 text-gate-gold',
    swatch: 'bg-gate-gold',
  },
  red: {
    key: 'red',
    label: 'Red',
    dot: 'error',
    help: 'Never auto runs; every step needs a person, destructive actions are refused.',
    selected: 'border-danger bg-danger/10 text-danger',
    swatch: 'bg-danger',
  },
};

// Coerce any string to a known level, defaulting to yellow (the safe deny by default position).
export function normalizeLevel(value: string | null | undefined): AutonomyLevel {
  const candidate = (value ?? '').trim().toLowerCase();
  return candidate === 'green' || candidate === 'yellow' || candidate === 'red' ? candidate : 'yellow';
}
