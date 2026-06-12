// Transport used by every Brain call.
//
// Browser companion: relies on the httpOnly session cookie and adds the CSRF token from
// the readable nexa_csrf cookie on state changing requests (double submit).
// Desktop wrapper: adds the bearer token from the secure store.

import { apiBase, desktopBearer } from './config';

const STATE_CHANGING = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

function readCookie(name: string): string | undefined {
  if (typeof document === 'undefined') return undefined;
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match && match[1] !== undefined ? decodeURIComponent(match[1]) : undefined;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? 'GET').toUpperCase();

  const bearer = desktopBearer();
  if (bearer) {
    headers.set('Authorization', `Bearer ${bearer}`);
  } else if (STATE_CHANGING.has(method)) {
    const csrf = readCookie('nexa_csrf');
    if (csrf) headers.set('X-CSRF-Token', csrf);
  }

  const response = await fetch(`${apiBase()}${path}`, {
    ...init,
    method,
    headers,
    credentials: 'include',
  });
  return response;
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await apiFetch(path, { ...init, headers });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const data = await response.json();
      message = (data as { detail?: string }).detail ?? message;
    } catch {
      // keep the status text
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
