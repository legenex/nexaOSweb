import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from './client';

type SystemHealth = Schemas['SystemHealth'];

export interface UplinkState {
  connected: boolean;
  uptimeSeconds: number | null;
  lastCheck: Date | null;
  checking: boolean;
  reconnect: () => void;
}

// The connection monitor. Polls the Brain health probe on an interval and exposes the live
// uplink state plus a manual reconnect that re-checks immediately. Mounting and unmounting the
// consumer starts and stops the polling, so only uplink dependent surfaces pay for it.
export function useConnectionMonitor(intervalMs = 15000): UplinkState {
  const [connected, setConnected] = useState(false);
  const [uptimeSeconds, setUptimeSeconds] = useState<number | null>(null);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);
  const [checking, setChecking] = useState(false);

  const check = useCallback(async () => {
    setChecking(true);
    try {
      const { data, error } = await api.GET('/system/health');
      if (!error && data) {
        const health = data as SystemHealth;
        setConnected(true);
        setUptimeSeconds(health.process.uptime_seconds);
      } else {
        setConnected(false);
      }
    } catch {
      setConnected(false);
    } finally {
      setLastCheck(new Date());
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void check();
    const id = window.setInterval(() => void check(), intervalMs);
    return () => window.clearInterval(id);
  }, [check, intervalMs]);

  return { connected, uptimeSeconds, lastCheck, checking, reconnect: () => void check() };
}
