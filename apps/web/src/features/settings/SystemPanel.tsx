import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { Button, Modal, MonoLabel, StatusDot } from '../../components/primitives';
import type { DotState } from '../../components/primitives';

type SystemHealth = Schemas['SystemHealth'];

function Row({ label, value, dot }: { label: string; value: string; dot?: DotState }) {
  return (
    <div className="flex items-center justify-between border-b border-line/60 py-2 last:border-b-0">
      <span className="mono-label">{label}</span>
      <span className="flex items-center gap-2 font-mono text-sm text-cream">
        {dot ? <StatusDot state={dot} /> : null}
        {value}
      </span>
    </div>
  );
}

function uptimeLabel(seconds: number): string {
  const s = Math.floor(seconds);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  const h = Math.floor(s / 3600);
  return `${h}h ${Math.floor((s % 3600) / 60)}m`;
}

export function SystemPanel() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [reachable, setReachable] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const { data, error } = await api.GET('/system/health');
    if (error || !data) {
      setReachable(false);
      return;
    }
    setReachable(true);
    setHealth(data as SystemHealth);
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(id);
  }, [load]);

  const restart = useCallback(async () => {
    setRestarting(true);
    setNotice(null);
    try {
      const { error } = await api.POST('/system/restart', { body: { confirm: true } });
      if (error) {
        setNotice('Restart was refused by the Brain.');
        return;
      }
      setConfirming(false);
      setNotice('Restart scheduled. The Brain will be back in a moment.');
      // Poll health back to life so the view reflects the fresh process.
      window.setTimeout(() => void load(), 2000);
    } finally {
      setRestarting(false);
    }
  }, [load]);

  const connectionDot: DotState = reachable && health ? 'live' : 'error';

  return (
    <div className="space-y-8">
      <section>
        <MonoLabel tone="accent">connection</MonoLabel>
        <div className="mt-3 rounded-glass border border-line bg-canvas/30 px-4">
          <Row
            label="brain"
            value={reachable ? 'reachable' : 'unreachable'}
            dot={connectionDot}
          />
          <Row label="version" value={health?.version ?? '—'} />
          <Row
            label="background sweep"
            value={health ? (health.sweep_enabled ? 'enabled' : 'disabled') : '—'}
          />
        </div>
      </section>

      <section>
        <MonoLabel tone="accent">database</MonoLabel>
        <div className="mt-3 rounded-glass border border-line bg-canvas/30 px-4">
          <Row
            label="status"
            value={health ? (health.database.connected ? 'connected' : 'down') : '—'}
            dot={health ? (health.database.connected ? 'live' : 'error') : undefined}
          />
          <Row label="dialect" value={health?.database.dialect ?? '—'} />
          <Row label="url" value={health?.database.url ?? '—'} />
          <Row
            label="migration"
            value={
              health
                ? health.migration.up_to_date
                  ? `up to date (${health.migration.head ?? '—'})`
                  : `behind (${health.migration.current ?? 'none'} / ${health.migration.head ?? '—'})`
                : '—'
            }
            dot={health ? (health.migration.up_to_date ? 'live' : 'warn') : undefined}
          />
        </div>
      </section>

      <section>
        <MonoLabel tone="accent">process</MonoLabel>
        <div className="mt-3 rounded-glass border border-line bg-canvas/30 px-4">
          <Row label="pid" value={health ? String(health.process.pid) : '—'} />
          <Row label="python" value={health?.process.python_version ?? '—'} />
          <Row
            label="uptime"
            value={health ? uptimeLabel(health.process.uptime_seconds) : '—'}
          />
          <Row label="started" value={health?.process.started_at ?? '—'} />
        </div>
      </section>

      <section className="rounded-glass border border-accent/40 bg-accent/5 p-4">
        <h3 className="text-sm font-semibold text-cream">Restart Brain</h3>
        <p className="mt-1 max-w-prose text-sm text-muted">
          Replaces the running Brain process. Use this to clear a stale process. In flight
          requests are dropped and the Brain is briefly unavailable while it comes back.
        </p>
        <Button variant="outline" className="mt-3" onClick={() => setConfirming(true)}>
          restart brain
        </Button>
        {notice ? <p className="mt-3 text-sm text-accent">{notice}</p> : null}
      </section>

      <Modal open={confirming} title="confirm restart" onClose={() => setConfirming(false)}>
        <p className="text-sm text-cream">
          Restart the Brain now? It will be unavailable for a few seconds while the fresh
          process takes over.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => setConfirming(false)}
            className="mono-label rounded-md border border-line px-3 py-1 hover:text-cream"
          >
            cancel
          </button>
          <Button variant="primary" disabled={restarting} onClick={() => void restart()}>
            {restarting ? 'restarting…' : 'yes, restart'}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
