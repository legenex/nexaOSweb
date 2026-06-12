import { isDesktop } from '../app/config';
import { MonoLabel } from './primitives';

// A custom titlebar for the frameless desktop window. The bar is a drag region; the
// controls call the Tauri window API. Rendered only inside the desktop wrapper.
async function windowAction(action: 'minimize' | 'toggleMaximize' | 'close') {
  try {
    const { getCurrentWindow } = await import('@tauri-apps/api/window');
    const win = getCurrentWindow();
    if (action === 'minimize') await win.minimize();
    else if (action === 'toggleMaximize') await win.toggleMaximize();
    else await win.close();
  } catch {
    // Not under Tauri.
  }
}

export function DesktopTitleBar() {
  if (!isDesktop()) return null;
  return (
    <div
      data-tauri-drag-region
      className="flex h-8 shrink-0 items-center justify-between border-b border-line bg-canvas px-3"
    >
      <MonoLabel tone="faint">nexaOSweb</MonoLabel>
      <div className="flex items-center gap-1">
        <button
          type="button"
          aria-label="Minimize"
          onClick={() => void windowAction('minimize')}
          className="rounded px-2 text-muted hover:text-cream"
        >
          –
        </button>
        <button
          type="button"
          aria-label="Maximize"
          onClick={() => void windowAction('toggleMaximize')}
          className="rounded px-2 text-muted hover:text-cream"
        >
          ▢
        </button>
        <button
          type="button"
          aria-label="Close"
          onClick={() => void windowAction('close')}
          className="rounded px-2 text-muted hover:text-danger"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
