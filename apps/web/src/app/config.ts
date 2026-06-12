// Runtime configuration. The web companion talks to /api (proxied in dev, served by
// Plesk Nginx in production). The desktop wrapper points at the hosted Brain and carries
// a bearer token from the OS secure store.

declare global {
  interface Window {
    __TAURI__?: unknown;
    __NEXA_BEARER__?: string;
    __NEXA_API_BASE__?: string;
  }
}

export const isDesktop = (): boolean =>
  typeof window !== 'undefined' && '__TAURI__' in window;

export const apiBase = (): string => {
  const fromEnv = import.meta.env.VITE_API_BASE as string | undefined;
  if (fromEnv) return fromEnv;
  if (typeof window !== 'undefined' && window.__NEXA_API_BASE__) return window.__NEXA_API_BASE__;
  return '/api';
};

// In the desktop wrapper the bearer is injected from the secure store (see apps/desktop).
export const desktopBearer = (): string | undefined =>
  typeof window !== 'undefined' ? window.__NEXA_BEARER__ : undefined;
