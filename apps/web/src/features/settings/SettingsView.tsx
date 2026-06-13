import { SETTINGS_TABS } from '../../app/nav';
import { KnowledgePanel } from './knowledge/KnowledgePanel';
import { ModelsAgentsPanel } from './ModelsAgentsPanel';
import { SystemPanel } from './SystemPanel';

// The Settings surface is driven by the sidebar: it expands inline to the seven sub tabs and
// routes straight to one via the composite settings:<subtab> nav key. This view renders the
// panel for the active sub tab. Models and Agents, Knowledge, and System keep their panels;
// the remaining tabs are built out over their endpoints in a following change.
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
  const current = SETTINGS_TABS.find((t) => t.key === tab) ?? SETTINGS_TABS[0]!;

  return (
    <section className="border-electric rounded-glass border border-line bg-surface/60 p-6">
      <div className="mono-label">settings / {current.key}</div>
      <h2 className="mb-4 mt-2 text-lg font-semibold text-cream">{current.label}</h2>
      <TabBody tabKey={current.key} />
    </section>
  );
}
