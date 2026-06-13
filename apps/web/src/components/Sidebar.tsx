import { NAV_ITEMS, SETTINGS_KEY, SETTINGS_TABS, navBaseKey, settingsRoute } from '../app/nav';
import { CommandBar } from './CommandBar';
import { ProfileFooter } from './ProfileFooter';

interface SidebarProps {
  active: string;
  onSelect: (key: string) => void;
}

// Fixed red gradient rail. The active row is a solid orange fill with a soft glow. The header
// holds the NexaOS wordmark and the global Ask Nexa control; the Settings row expands inline to
// its seven sub tabs while a Settings surface is active; the signed in profile sits at the foot.
export function Sidebar({ active, onSelect }: SidebarProps) {
  const baseKey = navBaseKey(active);

  return (
    <nav
      aria-label="Primary"
      className="flex h-full w-[206px] shrink-0 flex-col px-3 py-5"
      style={{
        background: 'linear-gradient(to bottom, var(--sidebar-top), var(--sidebar-bottom))',
      }}
    >
      <div className="mb-3 px-2">
        <div className="font-mono text-sm font-semibold tracking-[0.2em] text-cream">NEXA OS</div>
        <div className="mono-label mt-1 text-cream/70">personal ai os</div>
      </div>

      <div className="mb-4">
        <CommandBar />
      </div>

      <div className="scroll-themed flex flex-1 flex-col gap-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const isActive = baseKey === item.key;
          const isSettings = item.key === SETTINGS_KEY;
          return (
            <div key={item.key}>
              <button
                type="button"
                onClick={() => onSelect(item.key)}
                aria-current={isActive ? 'page' : undefined}
                aria-expanded={isSettings ? isActive : undefined}
                className={[
                  'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition',
                  isActive
                    ? 'bg-accent text-black shadow-[0_0_18px_rgba(255,115,32,0.5)]'
                    : 'text-cream/85 hover:bg-white/5',
                ].join(' ')}
              >
                <span className={isActive ? 'text-canvas' : 'text-accent-hi'} aria-hidden>
                  {item.glyph}
                </span>
                <span className="text-sm font-medium">{item.label}</span>
              </button>

              {/* Settings expands inline to its sub tabs while a Settings surface is active. */}
              {isSettings && isActive ? (
                <div className="mt-1 flex flex-col gap-0.5 border-l border-line pl-3">
                  {SETTINGS_TABS.map((tab) => {
                    const route = settingsRoute(tab.key);
                    // The default tab is also active when the bare "settings" key is set.
                    const isTabActive =
                      active === route ||
                      (active === SETTINGS_KEY && tab.key === SETTINGS_TABS[0]!.key);
                    return (
                      <button
                        key={tab.key}
                        type="button"
                        onClick={() => onSelect(route)}
                        aria-current={isTabActive ? 'page' : undefined}
                        className={[
                          'rounded-md px-3 py-1.5 text-left text-sm transition',
                          isTabActive
                            ? 'bg-accent/15 text-accent'
                            : 'text-cream/70 hover:bg-white/5',
                        ].join(' ')}
                      >
                        {tab.label}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      <ProfileFooter onNavigate={onSelect} />
    </nav>
  );
}
