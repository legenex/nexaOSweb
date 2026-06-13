import { NAV_ITEMS } from '../app/nav';
import { CommandBar } from './CommandBar';

interface SidebarProps {
  active: string;
  onSelect: (key: string) => void;
}

// Fixed red gradient rail. The active row is a solid orange fill with a soft glow. The header
// holds the NexaOS wordmark and the global Ask Nexa control, above the nav items.
export function Sidebar({ active, onSelect }: SidebarProps) {
  return (
    <nav
      aria-label="Primary"
      className="flex h-full w-[206px] shrink-0 flex-col gap-1 px-3 py-5"
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

      {NAV_ITEMS.map((item) => {
        const isActive = item.key === active;
        return (
          <button
            key={item.key}
            type="button"
            onClick={() => onSelect(item.key)}
            aria-current={isActive ? 'page' : undefined}
            className={[
              'flex items-center gap-3 rounded-lg px-3 py-2 text-left transition',
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
        );
      })}
    </nav>
  );
}
