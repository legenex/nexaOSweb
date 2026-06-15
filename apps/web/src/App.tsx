import { useEffect, useState } from 'react';

import { AuthProvider, useAuth } from './app/AuthProvider';
import { isDesktop } from './app/config';
import { DEFAULT_NAV_KEY, NAV_ITEMS, navBaseKey, settingsTabKey } from './app/nav';
import { NavigationContext } from './app/navigation';
import { DesktopTitleBar } from './components/DesktopTitleBar';
import { HoloObject } from './components/HoloObject';
import type { HoloVariant } from './components/HoloObject';
import { HolographicBackdrop } from './components/HolographicBackdrop';
import { Login } from './components/Login';
import { ResetPassword } from './components/ResetPassword';
import { MarketingHome } from './features/marketing/MarketingHome';
import { Sidebar } from './components/Sidebar';
import { UplinkLight } from './components/UplinkLight';
import { DashboardView } from './features/dashboard/DashboardView';
import { FlowPanorama } from './features/flow/FlowPanorama';
import { FocusView } from './features/focus/FocusView';
import { InsightsView } from './features/insights/InsightsView';
import { JournalView } from './features/journal/JournalView';
import { FlowProvider } from './features/flow/FlowProvider';
import { ProjectsView } from './features/projects/ProjectsView';
import { ResearchView } from './features/research/ResearchView';
import { SettingsView } from './features/settings/SettingsView';
import { TasksView } from './features/tasks/TasksView';

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
      return <TasksView />;
    case 'focus':
      return <FocusView />;
    default:
      return <Placeholder label={label} />;
  }
}

// Every surface gets a holographic object, rendered once and fixed in the corner by the shell.
// Each surface maps to a distinct variant; unlisted keys fall back to the dashboard form.
const HOLO_VARIANT: Record<string, HoloVariant> = {
  dashboard: 'dashboard',
  insights: 'insights',
  research: 'research',
  projects: 'projects',
  'project-builder': 'projects',
  journal: 'insights',
  tasks: 'projects',
  focus: 'research',
  settings: 'dashboard',
};

const holoVariantFor = (key: string): HoloVariant => HOLO_VARIANT[key] ?? 'dashboard';

// The page title. Flow Builder reads Project Flow Builder in the header while the sidebar and
// route key stay Flow Builder and project-builder.
const pageTitleFor = (key: string, label: string): string =>
  key === 'project-builder' ? 'Project Flow Builder' : label;

function Shell() {
  const [active, setActive] = useState(DEFAULT_NAV_KEY);
  const baseKey = navBaseKey(active);
  const current = NAV_ITEMS.find((item) => item.key === baseKey) ?? NAV_ITEMS[0]!;

  return (
    <FlowProvider>
      <NavigationContext.Provider value={setActive}>
        <div className="relative flex h-screen w-screen flex-col overflow-hidden">
          <DesktopTitleBar />
          {/* One holographic object, fixed in the bottom right of the viewport behind all
              content so it never clips on scroll and is present on every surface. It is
              pointer-events-none and sits on z-0, the content sits on z-10. */}
          <div
            aria-hidden
            className="pointer-events-none fixed bottom-0 right-0 z-0 h-[42vmin] w-[42vmin] overflow-hidden"
          >
            <HoloObject variant={holoVariantFor(baseKey)} />
          </div>
          <div className="relative z-10 flex flex-1 overflow-hidden">
            <Sidebar active={active} onSelect={setActive} />
            <main className="relative flex-1 overflow-auto p-8">
              <HolographicBackdrop />
              <div className="relative z-10 mb-4">
                <PageHeader
                  title={pageTitleFor(baseKey, current.label)}
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

// The public surface for anonymous web visitors: the marketing homepage by default, and the
// sign-in form at #signin. A hash route keeps the sign-in link shareable and the browser back
// button working without pulling in a router. The desktop wrapper authenticates with its bearer
// and never lands here, so its anonymous state goes straight to the login form.
function PublicSite() {
  const [hash, setHash] = useState<string>(() =>
    typeof window !== 'undefined' ? window.location.hash : '',
  );

  useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const go = (next: string) => {
    window.location.hash = next;
  };

  // The emailed reset link lands at #reset?token=... The token rides in the hash query so it never
  // hits the server logs as a path. Anything starting with #reset shows the reset screen.
  if (hash.startsWith('#reset')) {
    const queryStart = hash.indexOf('?');
    const token =
      queryStart === -1
        ? ''
        : new URLSearchParams(hash.slice(queryStart + 1)).get('token') ?? '';
    return (
      <div className="relative h-full">
        <HolographicBackdrop />
        <ResetPassword token={token} onDone={() => go('signin')} onBack={() => go('')} />
      </div>
    );
  }

  if (hash === '#signin') {
    return (
      <div className="relative h-full">
        <HolographicBackdrop />
        <Login onBack={() => go('')} />
      </div>
    );
  }
  return <MarketingHome onSignIn={() => go('signin')} />;
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
  if (status === 'anonymous') return isDesktop() ? <Login /> : <PublicSite />;
  return <Shell />;
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
