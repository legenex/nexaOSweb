import { useState } from 'react';

import { AuthProvider, useAuth } from './app/AuthProvider';
import { DEFAULT_NAV_KEY, NAV_ITEMS } from './app/nav';
import { NavigationContext } from './app/navigation';
import { ComingSoon } from './components/ComingSoon';
import { DesktopTitleBar } from './components/DesktopTitleBar';
import { HoloObject } from './components/HoloObject';
import type { HoloVariant } from './components/HoloObject';
import { HolographicBackdrop } from './components/HolographicBackdrop';
import { Login } from './components/Login';
import { Sidebar } from './components/Sidebar';
import { FlowPanorama } from './features/flow/FlowPanorama';
import { FlowProvider } from './features/flow/FlowProvider';
import { ProjectsView } from './features/projects/ProjectsView';
import { SettingsView } from './features/settings/SettingsView';

function PageHeader({ title, label }: { title: string; label: string }) {
  return (
    <header className="mb-6">
      <h1 className="text-[22px] font-semibold text-cream">{title}</h1>
      <div className="mt-1 flex items-center gap-2">
        <span
          aria-hidden
          className="inline-block h-2 w-2 rounded-full bg-status-green shadow-[0_0_8px_var(--status-green)]"
        />
        <span className="mono-label">{label}</span>
      </div>
    </header>
  );
}

// A neutral resolving surface for routes whose full view is a later milestone.
function Placeholder({ label }: { label: string }) {
  return (
    <section className="rounded-glass border border-line bg-surface/60 p-6">
      <p className="text-sm text-muted">{label} is part of the nexaOSweb shell.</p>
    </section>
  );
}

// Every nav key resolves to a surface. Project Builder renders the internal Flow panorama.
function Surface({ active, label }: { active: string; label: string }) {
  switch (active) {
    case 'project-builder':
      return <FlowPanorama />;
    case 'projects':
      return <ProjectsView />;
    case 'settings':
      return <SettingsView />;
    case 'journal':
      return (
        <ComingSoon
          title="Journal"
          blurb="Capture notes and daily reflections that feed the nightly Dreaming consolidation."
        />
      );
    case 'tasks':
      return (
        <ComingSoon
          title="Tasks"
          blurb="Track what to do, with reminders folded in, ranked by Focus."
        />
      );
    case 'focus':
      return (
        <ComingSoon
          title="Focus"
          blurb="Rank the day's work from the Knowledge base and hold you to what matters most."
        />
      );
    default:
      return <Placeholder label={label} />;
  }
}

// Each built out surface gets its own holographic object. Keys not listed render none.
const HOLO_VARIANT: Record<string, HoloVariant> = {
  dashboard: 'dashboard',
  insights: 'insights',
  research: 'research',
  'project-builder': 'project-builder',
  projects: 'projects',
};

function Shell() {
  const { me, logout } = useAuth();
  const [active, setActive] = useState(DEFAULT_NAV_KEY);
  const current = NAV_ITEMS.find((item) => item.key === active) ?? NAV_ITEMS[0]!;

  return (
    <FlowProvider>
    <NavigationContext.Provider value={setActive}>
    <div className="flex h-screen w-screen flex-col overflow-hidden">
      <DesktopTitleBar />
      <div className="flex flex-1 overflow-hidden">
      <Sidebar active={active} onSelect={setActive} />
      <main className="relative flex-1 overflow-auto p-8">
        <HolographicBackdrop />
        {HOLO_VARIANT[active] ? (
          <HoloObject
            variant={HOLO_VARIANT[active]!}
            className="pointer-events-none absolute right-6 top-4 z-0 opacity-60"
          />
        ) : null}
        <div className="relative z-10 mb-4 flex items-center justify-between">
          <PageHeader title={current.label} label={`${current.key} ${current.description}`} />
          <button
            type="button"
            onClick={() => void logout()}
            className="mono-label rounded-md border border-line px-3 py-1 hover:text-accent"
          >
            {me?.email ? `sign out ${me.email}` : 'sign out'}
          </button>
        </div>
        <div className="relative z-10">
          <Surface active={active} label={current.label} />
        </div>
      </main>
      </div>
    </div>
    </NavigationContext.Provider>
    </FlowProvider>
  );
}

function Gate() {
  const { status } = useAuth();
  if (status === 'loading') {
    return (
      <div className="flex h-screen items-center justify-center">
        <span className="mono-label">loading</span>
      </div>
    );
  }
  if (status === 'anonymous') return <Login />;
  return <Shell />;
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
