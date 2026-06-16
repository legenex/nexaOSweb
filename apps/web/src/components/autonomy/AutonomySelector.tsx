import { useRef } from 'react';

import { MonoLabel, StatusDot } from '../primitives';
import { AUTONOMY_LEVELS, LEVEL_META } from './levels';
import type { AutonomyLevel } from './levels';

// The green, yellow, red autonomy selector, a shared control reused on the Task detail (per task)
// and on the Projects and Project Builder surfaces (project default). It is a true radio group:
// arrow keys move and select, a roving tabindex keeps a single tab stop, and every option is
// labelled. Colors come only from CSS variables through the level metadata; orange stays brand.
export function AutonomySelector({
  value,
  onChange,
  label = 'Autonomy',
  hint,
  disabled = false,
  busy = false,
  size = 'md',
}: {
  value: AutonomyLevel;
  onChange: (level: AutonomyLevel) => void;
  label?: string;
  hint?: string;
  disabled?: boolean;
  busy?: boolean;
  size?: 'sm' | 'md';
}) {
  const buttonsRef = useRef<(HTMLButtonElement | null)[]>([]);
  const locked = disabled || busy;

  const move = (delta: number) => {
    const current = AUTONOMY_LEVELS.indexOf(value);
    const start = current < 0 ? 0 : current;
    const next = (start + delta + AUTONOMY_LEVELS.length) % AUTONOMY_LEVELS.length;
    const level = AUTONOMY_LEVELS[next]!;
    onChange(level);
    buttonsRef.current[next]?.focus();
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (locked) return;
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        event.preventDefault();
        move(1);
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        event.preventDefault();
        move(-1);
        break;
      case 'Home':
        event.preventDefault();
        onChange(AUTONOMY_LEVELS[0]!);
        buttonsRef.current[0]?.focus();
        break;
      case 'End': {
        event.preventDefault();
        const last = AUTONOMY_LEVELS.length - 1;
        onChange(AUTONOMY_LEVELS[last]!);
        buttonsRef.current[last]?.focus();
        break;
      }
      default:
        break;
    }
  };

  const pad = size === 'sm' ? 'px-2 py-1' : 'px-3 py-1.5';
  const selectedMeta = LEVEL_META[value];

  return (
    <div className={locked ? 'opacity-60' : ''}>
      {label ? <MonoLabel tone="faint">{label}</MonoLabel> : null}
      <div
        role="radiogroup"
        aria-label={label}
        onKeyDown={onKeyDown}
        className={`mt-1 inline-flex flex-wrap items-center gap-1.5 ${label ? '' : 'mt-0'}`}
      >
        {AUTONOMY_LEVELS.map((level, index) => {
          const meta = LEVEL_META[level];
          const isSelected = level === value;
          return (
            <button
              key={level}
              type="button"
              ref={(element) => {
                buttonsRef.current[index] = element;
              }}
              role="radio"
              aria-checked={isSelected}
              aria-label={`${meta.label} autonomy: ${meta.help}`}
              title={meta.help}
              tabIndex={isSelected ? 0 : -1}
              disabled={locked}
              onClick={() => !locked && onChange(level)}
              className={[
                'inline-flex items-center gap-1.5 rounded-md border font-mono text-[0.66rem] uppercase tracking-[0.1em] transition',
                pad,
                isSelected ? meta.selected : 'border-line text-muted hover:text-cream',
                locked ? 'cursor-not-allowed' : 'cursor-pointer',
              ].join(' ')}
            >
              <StatusDot state={meta.dot} />
              {meta.label}
            </button>
          );
        })}
      </div>
      {hint ? <p className="mt-1 mono-meta text-faint">{hint}</p> : null}
      {!hint && selectedMeta ? (
        <p className="mt-1 mono-meta text-faint">{selectedMeta.help}</p>
      ) : null}
    </div>
  );
}
