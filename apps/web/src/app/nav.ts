export interface NavItem {
  key: string;
  label: string;
  glyph: string;
  description: string;
}

// The sidebar nav. Flow is the home of the seven stage panorama.
export const NAV_ITEMS: NavItem[] = [
  { key: 'flow', label: 'Flow', glyph: '◇', description: 'The seven stage pipeline' },
  { key: 'projects', label: 'Projects', glyph: '▣', description: 'Maintained projects' },
  { key: 'research', label: 'Research', glyph: '◈', description: 'Grounded research' },
  { key: 'tasks', label: 'Tasks', glyph: '✓', description: 'Things to do' },
  { key: 'journal', label: 'Journal', glyph: '✎', description: 'Notes and reflections' },
  { key: 'settings', label: 'Settings', glyph: '⚙', description: 'Intake knobs' },
];
