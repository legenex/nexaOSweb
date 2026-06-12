export interface NavItem {
  key: string;
  label: string;
  glyph: string;
  description: string;
}

// The canonical nine item sidebar, top to bottom. Dashboard is the default landing surface.
// Project Builder is the user facing name and route for the internal Flow pipeline. The
// internal module names (FlowPanorama, FlowProvider, features/flow) stay Flow on purpose.
export const NAV_ITEMS: NavItem[] = [
  { key: 'dashboard', label: 'Dashboard', glyph: '⬡', description: 'Your day at a glance' },
  { key: 'insights', label: 'Insights', glyph: '◴', description: 'Signals and trends' },
  { key: 'journal', label: 'Journal', glyph: '✎', description: 'Notes and reflections' },
  { key: 'tasks', label: 'Tasks', glyph: '✓', description: 'Things to do' },
  { key: 'research', label: 'Research', glyph: '◈', description: 'Grounded research' },
  { key: 'focus', label: 'Focus', glyph: '◎', description: 'Ranked work' },
  { key: 'project-builder', label: 'Project Builder', glyph: '◇', description: 'The seven stage pipeline' },
  { key: 'projects', label: 'Projects', glyph: '▣', description: 'Maintained projects' },
  { key: 'settings', label: 'Settings', glyph: '⚙', description: 'Configuration' },
];

// The default landing route, top of the sidebar.
export const DEFAULT_NAV_KEY = 'dashboard';

export interface SettingsTab {
  key: string;
  label: string;
}

// Settings sub tabs, in canonical order.
export const SETTINGS_TABS: SettingsTab[] = [
  { key: 'general', label: 'General' },
  { key: 'users', label: 'Users' },
  { key: 'integrations', label: 'Integrations' },
  { key: 'knowledge', label: 'Knowledge' },
  { key: 'skills-connectors', label: 'Skills and Connectors' },
  { key: 'models-agents', label: 'Models and Agents' },
  { key: 'system', label: 'System' },
];
