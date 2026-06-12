import { useState } from 'react';

import { AuthProvider, useAuth } from './app/AuthProvider';
import { NAV_ITEMS } from './app/nav';
import { NavigationContext } from './app/navigation';
import { DesktopTitleBar } from './components/DesktopTitleBar';
import { HolographicBackdrop } from './components/HolographicBackdrop';
import { Login } from './components/Login';
import { Sidebar } from './components/Sidebar';
import { FlowPanorama } from './features/flow/FlowPanorama';
import { FlowProvider } from './features/flow/FlowProvider';
import { ProjectsView } from './features/projects/ProjectsView';

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

function Shell() {
  const { me, logout } = useAuth();
  const [active, setActive] = useState('flow');
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
        <div className="mb-4 flex items-center justify-between">
          <PageHeader title={current.label} label={`${current.key} ${current.description}`} />
          <button
            type="button"
            onClick={() => void logout()}
            className="mono-label rounded-md border border-line px-3 py-1 hover:text-accent"
          >
            {me?.email ? `sign out ${me.email}` : 'sign out'}
          </button>
        </div>
        {active === 'flow' ? (
          <FlowPanorama />
        ) : active === 'projects' ? (
          <ProjectsView />
        ) : (
          <section className="rounded-glass border border-line bg-surface/60 p-6">
            <p className="text-sm text-muted">
              This tab is part of the nexaOSweb shell. Flow is the primary surface for v1.
            </p>
          </section>
        )}
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
