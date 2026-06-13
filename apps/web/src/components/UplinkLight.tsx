import { useState } from 'react';

import { useConnectionMonitor } from '../app/useConnectionMonitor';
import { StatusDot } from './primitives';

function uptimeLabel(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}

// The uplink status light: a StatusDot driven by the connection monitor, shown only on surfaces
// that depend on a live Brain. Hover (or focus) reveals uptime and last check when connected, or
// a Disconnected state with a working Reconnect when down.
export function UplinkLight() {
  const { connected, uptimeSeconds, lastCheck, checking, reconnect } = useConnectionMonitor();
  const [open, setOpen] = useState(false);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        aria-label={connected ? 'Uplink connected' : 'Uplink disconnected'}
        className="inline-flex items-center rounded-full outline-none focus-visible:ring-1 focus-visible:ring-accent"
      >
        <StatusDot state={connected ? 'live' : 'error'} />
      </button>

      {open ? (
        <span
          role="status"
          className="absolute left-0 top-full z-40 mt-2 w-56 rounded-glass border border-line bg-surface p-3 text-left shadow-xl"
        >
          {connected ? (
            <>
              <span className="mono-label text-status-green">uplink connected</span>
              <span className="mt-1 block text-xs text-muted">
                uptime {uptimeSeconds != null ? uptimeLabel(uptimeSeconds) : 'unknown'}
              </span>
              <span className="block text-xs text-faint">
                last check {lastCheck ? lastCheck.toLocaleTimeString() : 'just now'}
              </span>
            </>
          ) : (
            <>
              <span className="mono-label text-danger">disconnected</span>
              <span className="mt-1 block text-xs text-muted">
                The Brain uplink is unreachable.
              </span>
              <button
                type="button"
                onClick={() => reconnect()}
                disabled={checking}
                className="mono-label mt-2 rounded-md border border-accent px-2 py-1 text-accent hover:bg-accent/10 disabled:opacity-50"
              >
                {checking ? 'reconnecting…' : 'reconnect'}
              </button>
            </>
          )}
        </span>
      ) : null}
    </span>
  );
}
