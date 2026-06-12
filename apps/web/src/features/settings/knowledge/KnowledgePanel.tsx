import { useState } from 'react';

import { ApiConnectionsPanel } from './ApiConnectionsPanel';
import { DreamingReview } from './DreamingReview';
import { ScopeList } from './ScopeList';

// Internal Knowledge tabs, in the canonical order from CLAUDE.md.
const KNOWLEDGE_TABS = [
  { key: 'general', label: 'General' },
  { key: 'personal', label: 'Personal' },
  { key: 'development', label: 'Development' },
  { key: 'api', label: 'API connections' },
  { key: 'dreaming', label: 'Dreaming' },
] as const;

type KnowledgeTabKey = (typeof KNOWLEDGE_TABS)[number]['key'];

export function KnowledgePanel() {
  const [tab, setTab] = useState<KnowledgeTabKey>('general');
  // Bumped when a Dreaming candidate is accepted so a scope list re-reads on next view.
  const [dataVersion, setDataVersion] = useState(0);

  return (
    <div>
      <nav aria-label="Knowledge" className="mb-5 flex flex-wrap gap-1 border-b border-line pb-3">
        {KNOWLEDGE_TABS.map((t) => {
          const isActive = t.key === tab;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              aria-current={isActive ? 'page' : undefined}
              className={[
                'rounded-md px-3 py-1.5 text-sm transition',
                isActive ? 'bg-accent text-canvas' : 'text-cream/80 hover:bg-white/5',
              ].join(' ')}
            >
              {t.label}
            </button>
          );
        })}
      </nav>

      {tab === 'general' || tab === 'personal' || tab === 'development' ? (
        <ScopeList key={`${tab}-${dataVersion}`} scope={tab} />
      ) : tab === 'api' ? (
        <ApiConnectionsPanel />
      ) : (
        <DreamingReview onAccepted={() => setDataVersion((value) => value + 1)} />
      )}
    </div>
  );
}
