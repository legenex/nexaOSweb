import { useState } from 'react';

import { SETTINGS_TABS } from '../../app/nav';
import { ModelsAgentsPanel } from './ModelsAgentsPanel';
import { SystemPanel } from './SystemPanel';

// What each settings sub tab will hold. One line each, so the routes read as intent until the
// real panels land. Orange is the only brand color, all surfaces come from CSS variables.
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
    case 'models-agents':
      return <ModelsAgentsPanel />;
    case 'system':
      return <SystemPanel />;
    default:
      return <p className="mt-3 max-w-prose text-sm text-muted">{TAB_BLURB[tabKey]}</p>;
  }
}

export function SettingsView() {
  const [tab, setTab] = useState(SETTINGS_TABS[0]!.key);
  const current = SETTINGS_TABS.find((t) => t.key === tab) ?? SETTINGS_TABS[0]!;

  return (
    <section className="flex gap-6">
      <nav aria-label="Settings" className="flex w-[180px] shrink-0 flex-col gap-1">
        {SETTINGS_TABS.map((t) => {
          const isActive = t.key === tab;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              aria-current={isActive ? 'page' : undefined}
              className={[
                'rounded-md px-3 py-2 text-left text-sm transition',
                isActive ? 'bg-accent text-canvas' : 'text-cream/80 hover:bg-white/5',
              ].join(' ')}
            >
              {t.label}
            </button>
          );
        })}
      </nav>

      <div className="flex-1 rounded-glass border border-line bg-surface/60 p-6">
        <div className="mono-label">settings / {current.key}</div>
        <h2 className="mt-2 mb-4 text-lg font-semibold text-cream">{current.label}</h2>
        <TabBody tabKey={current.key} />
      </div>
    </section>
  );
}
