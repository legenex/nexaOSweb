import { useState } from 'react';

import { AuthProvider, useAuth } from './app/AuthProvider';
import { DEFAULT_NAV_KEY, NAV_ITEMS, navBaseKey, settingsTabKey } from './app/nav';
import { NavigationContext } from './app/navigation';
import { ComingSoon } from './components/ComingSoon';
import { DesktopTitleBar } from './components/DesktopTitleBar';
import { HoloObject } from './components/HoloObject';
import type { HoloVariant } from './components/HoloObject';
import { HolographicBackdrop } from './components/HolographicBackdrop';
import { Login } from './components/Login';
import { Sidebar } from './components/Sidebar';
import { UplinkLight } from './components/UplinkLight';
import { DashboardView } from './features/dashboard/DashboardView';
import { FlowPanorama } from './features/flow/FlowPanorama';
import { InsightsView } from './features/insights/InsightsView';
import { JournalView } from './features/journal/JournalView';
import { FlowProvider } from './features/flow/FlowProvider';
import { ProjectsView } from './features/projects/ProjectsView';
import { ResearchView } from './features/research/ResearchView';
import { SettingsView } from './features/settings/SettingsView';

// Surfaces that depend on a live Brain uplink show the status light; local or cached pages do not.
const UPLINK_SURFACES = new Set(['research', 'projects', 'project-builder']);

function PageHeader({ title, label, uplink }: { title: string; label: string; uplink: boolean }) {
  return (
    <header className="mb-6">
      <h1 className="text-[22px] font-semibold text-cream">{title}</h1>
      <div className="mt-1 flex items-center gap-2">
        {uplink ? <UplinkLight /> : null}
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
// Settings uses a composite key (settings or settings:<subtab>), so we switch on the base key
// and pass the resolved sub tab through to the SettingsView.
function Surface({ active, label }: { active: string; label: string }) {
  switch (navBaseKey(active)) {
    case 'dashboard':
      return <DashboardView />;
    case 'insights':
      return <InsightsView />;
    case 'project-builder':
      return <FlowPanorama />;
    case 'projects':
      return <ProjectsView />;
    case 'research':
      return <ResearchView />;
    case 'settings':
      return <SettingsView tab={settingsTabKey(active)} />;
    case 'journal':
      return <JournalView />;
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

// Each built out surface gets its own distinct holographic object. Keys not listed render none,
// so Project Builder (its own panorama) and the coming soon pages show no extra object.
const HOLO_VARIANT: Record<string, HoloVariant> = {
  dashboard: 'dashboard',
  insights: 'insights',
  research: 'research',
  projects: 'projects',
};

function Shell() {
  const [active, setActive] = useState(DEFAULT_NAV_KEY);
  const baseKey = navBaseKey(active);
  const current = NAV_ITEMS.find((item) => item.key === baseKey) ?? NAV_ITEMS[0]!;

  return (
    <FlowProvider>
      <NavigationContext.Provider value={setActive}>
        <div className="flex h-screen w-screen flex-col overflow-hidden">
          <DesktopTitleBar />
          <div className="flex flex-1 overflow-hidden">
            <Sidebar active={active} onSelect={setActive} />
            <main className="relative flex-1 overflow-auto p-8">
              <HolographicBackdrop />
              {HOLO_VARIANT[baseKey] ? (
                // A full bleed clipping layer behind the content. It is absolutely positioned and
                // overflow hidden, so the large object can bleed past the edges without ever adding
                // a scrollbar or shifting layout, and pointer-events-none keeps it from blocking the
                // content above it (which sits on z-10).
                <div
                  aria-hidden
                  className="pointer-events-none absolute inset-0 z-0 overflow-hidden"
                >
                  <HoloObject variant={HOLO_VARIANT[baseKey]!} />
                </div>
              ) : null}
              <div className="relative z-10 mb-4">
                <PageHeader
                  title={current.label}
                  label={`${current.key} ${current.description}`}
                  uplink={UPLINK_SURFACES.has(baseKey)}
                />
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
