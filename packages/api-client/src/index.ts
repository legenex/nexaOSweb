// Typed Brain client, generated from the Brain OpenAPI.
//
// The path and schema types live in ./generated/schema.d.ts and are produced by
// `pnpm gen:client`. openapi-fetch turns them into a fully typed GET/POST/PATCH client.

import createClient from 'openapi-fetch';
import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';

export type { components, paths };
export type Schemas = components['schemas'];
export type ApiClient = Client<paths>;

export interface ClientOptions {
  baseUrl: string;
}

export function createApiClient({ baseUrl }: ClientOptions): ApiClient {
  // credentials include so the browser sends the httpOnly session cookie.
  return createClient<paths>({ baseUrl, credentials: 'include' });
}
