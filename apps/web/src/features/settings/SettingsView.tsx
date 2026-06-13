import { SETTINGS_TABS, settingsRoute } from '../../app/nav';
import { useNavigation } from '../../app/navigation';
import { GeneralPanel } from './GeneralPanel';
import { IntegrationsPanel } from './IntegrationsPanel';
import { KnowledgePanel } from './knowledge/KnowledgePanel';
import { ModelsAgentsPanel } from './ModelsAgentsPanel';
import { SkillsPanel } from './SkillsPanel';
import { SystemPanel } from './SystemPanel';
import { UsersPanel } from './UsersPanel';

// The Settings surface. The active sub tab comes from the route (settings:<subtab>), so the
// sidebar dropdown shortcut and the in-page tab bar below read the same state and always agree:
// both navigate through the shared NavigationContext, which updates the single active key.
const TAB_BLURB: Record<string, string> = {
  general: 'Workspace name, locale, and the defaults that frame every other surface.',
  users: 'People with access, their roles, and invitations.',
  integrations: 'Connected providers and the accounts the Brain may act through.',
  knowledge: 'The Knowledge base and the Dreaming candidate review queue.',
  'skills-connectors': 'Installed skills and the connectors that extend what the system can do.',
  'models-agents': 'Semantic model keys and the agents that run the pipeline.',
  system: 'Health, storage, backups, and the low level controls.',
};

function TabBody({ tabKey }: { tabKey: string }) {
  switch (tabKey) {
    case 'general':
      return <GeneralPanel />;
    case 'users':
      return <UsersPanel />;
    case 'integrations':
      return <IntegrationsPanel />;
    case 'skills-connectors':
      return <SkillsPanel />;
    case 'knowledge':
      return <KnowledgePanel />;
    case 'models-agents':
      return <ModelsAgentsPanel />;
    case 'system':
      return <SystemPanel />;
    default:
      return <p className="mt-3 max-w-prose text-sm text-muted">{TAB_BLURB[tabKey]}</p>;
  }
}

export function SettingsView({ tab }: { tab: string }) {
  const navigate = useNavigation();
  const current = SETTINGS_TABS.find((t) => t.key === tab) ?? SETTINGS_TABS[0]!;

  return (
    <section className="space-y-5">
      {/* In-page horizontal tab bar across all seven sections, matching the project workspace
          tab pattern. Clicking a tab navigates through the same route the sidebar dropdown uses,
          so the two stay in sync on the active section. */}
      <div
        role="tablist"
        aria-label="Settings tabs"
        className="flex flex-wrap gap-1 border-b border-line"
      >
        {SETTINGS_TABS.map((t) => {
          const isActive = t.key === current.key;
          return (
            <button
              key={t.key}
              role="tab"
              aria-selected={isActive}
              onClick={() => navigate(settingsRoute(t.key))}
              className={`-mb-px border-b-2 px-3 py-2 text-sm transition ${
                isActive
                  ? 'border-accent text-accent'
                  : 'border-transparent text-muted hover:text-cream'
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      <div className="border-electric rounded-glass border border-line bg-surface/60 p-6">
        <div className="mono-label">settings / {current.key}</div>
        <h2 className="mb-4 mt-2 text-lg font-semibold text-cream">{current.label}</h2>
        <TabBody tabKey={current.key} />
      </div>
    </section>
  );
}
