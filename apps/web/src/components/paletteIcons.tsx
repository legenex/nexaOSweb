// Line icons for the command palette upload affordances. Drawn with currentColor so the
// colour comes from the surrounding text colour (a brand variable), never a hardcoded hex.

const base = {
  width: 18,
  height: 18,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.7,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

export function DocumentIcon() {
  return (
    <svg {...base} aria-hidden>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6M9 17h6" />
    </svg>
  );
}

export function ImageIcon() {
  return (
    <svg {...base} aria-hidden>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="8.5" cy="9" r="1.5" />
      <path d="M21 16l-5-5L5 20" />
    </svg>
  );
}

export function VoiceIcon() {
  return (
    <svg {...base} aria-hidden>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M6 11a6 6 0 0 0 12 0" />
      <path d="M12 17v4M9 21h6" />
    </svg>
  );
}

export function JournalIcon() {
  return (
    <svg {...base} aria-hidden>
      <path d="M5 4a2 2 0 0 1 2-2h11v18H7a2 2 0 0 0-2 2z" />
      <path d="M5 20a2 2 0 0 1 2-2h11" />
      <path d="M9 6h6" />
    </svg>
  );
}
