// The wired Brain client. Base URL comes from config: /api in the browser (dev proxy or
// Plesk Nginx) and the hosted Brain in the desktop wrapper. Middleware adds the desktop
// bearer or the browser CSRF token, matching the raw transport in api.ts.

import { createApiClient } from '@nexaosweb/api-client';

import { apiBase, desktopBearer } from './config';

const STATE_CHANGING = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

function readCookie(name: string): string | undefined {
  if (typeof document === 'undefined') return undefined;
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match && match[1] !== undefined ? decodeURIComponent(match[1]) : undefined;
}

export const api = createApiClient({ baseUrl: apiBase() });

api.use({
  onRequest({ request }) {
    const bearer = desktopBearer();
    if (bearer) {
      request.headers.set('Authorization', `Bearer ${bearer}`);
    } else if (STATE_CHANGING.has(request.method.toUpperCase())) {
      const csrf = readCookie('nexa_csrf');
      if (csrf) request.headers.set('X-CSRF-Token', csrf);
    }
    return request;
  },
});
