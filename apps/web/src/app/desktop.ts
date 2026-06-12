// Desktop bootstrap. When running inside the Tauri wrapper, ask the Rust side for the API
// base and the bearer token from the OS secure store, and expose them as globals the
// transport reads. A no op in the browser.

import { isDesktop } from './config';

interface DesktopConfig {
  api_base: string;
  bearer: string | null;
}

export async function initDesktop(): Promise<void> {
  if (!isDesktop()) return;
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    const config = await invoke<DesktopConfig>('get_config');
    if (config.api_base) window.__NEXA_API_BASE__ = config.api_base;
    if (config.bearer) window.__NEXA_BEARER__ = config.bearer;
  } catch {
    // Not running under Tauri, or the command is unavailable. Fall back to defaults.
  }
}
