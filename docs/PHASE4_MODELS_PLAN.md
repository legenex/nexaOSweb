# Phase 4: Dynamic Model Providers (plan only)

Status: plan, no code. This document records the design for connecting provider accounts and
discovering their models dynamically from Settings, Models and Agents. It is the authoritative
record for the build prompts that follow. It reuses the existing secret store
(`services/brain/app/security/secret_store.py`) and the credential fulfil pattern
(`services/brain/app/agents/readiness.py`, `services/brain/app/routers/integrations.py`).

## Goal and current state

Today the model router (`services/brain/app/router/model_router.py`) maps semantic keys to concrete
model ids in `services/brain/config/models.yaml`, and litellm picks up provider keys implicitly from
the environment. Keys are declared in `services/brain/app/settings.py`
(`anthropic_api_key`, `openai_api_key`, `gemini_api_key`, `tavily_api_key`). There is no UI to
connect a provider account, no discovery of which models an account can actually use, and the
router does not pass the key to litellm explicitly.

Phase 4 adds: a Settings flow to connect a provider account (key written to the secret store, never
returned), per provider model discovery, an enabled flag on discovered models, and a router that
reads the key from the store first and passes it to litellm explicitly. The model id stays a config
value; only enabled, discovered models can be selected when remapping a semantic key.

Canonical provider ids used internally (these are the `Integration.provider` values and the secret
slugs): `anthropic`, `openai`, `gemini`, `tavily`. The UI labels Gemini as "Google (Gemini)". We
deliberately use `gemini` rather than `google` for the secret slug and provider id so a model
provider account never collides with a future Google OAuth connector (Calendar, Drive), which would
also want the name `google`. The kind discriminator below makes that separation explicit.

## 1. Storage decision: a dedicated server wide provider table

Decision (as built, reconciled): use a dedicated `ProviderCredential` table
(`services/brain/app/models/provider.py`), not the per user `Integration` row. This document
originally proposed reusing `Integration`; the implementation chose a separate table for a clear
reason, recorded here so code and plan agree. Reuse was preferred only "unless a clear reason not
to" (the prompt), and the reason below is that clear reason.

Why a dedicated table rather than reusing `Integration`:

- Scope. `Integration` is per user (it carries `user_id`, and readiness reads it per user). A model
  provider key is server wide: the Brain runs every user's AI features on it. Storing a server wide
  credential on a per user row would force an arbitrary owning user and confuse the readiness
  per user reads. `ProviderCredential` is keyed by `provider` alone, one row per provider, which
  matches how the key is actually scoped.
- Separation of concerns. Model provider accounts (anthropic, openai, gemini) and the per user OAuth
  and tool connectors (the `Integration` rows) are different lifecycles with different authz (model
  keys are owner or admin only, server wide). Keeping them in separate tables avoids a `kind`
  discriminator and avoids the `google` name collision between a Gemini account and a future Google
  connector entirely, because the two never share a table.
- The reuse benefits still hold without sharing the row. `ProviderCredential` still records the key
  by reference only (`credentials_ref = secret://<provider>`), still writes the secret through the
  same `store_secret`, and is still covered by the same redaction guard. None of the reference only
  discipline is lost by not sharing `Integration`.

`ProviderCredential` columns: `id`, `provider` (unique, indexed), `status` (`connected` once a key
is stored, `available` otherwise), `credentials_ref` (a `secret://` reference, never the value), and
`hint` (the masked last four, see section 3). A connected row looks like: `provider="anthropic"`,
`status="connected"`, `credentials_ref="secret://anthropic"`, `hint="****3xQk"`.

Gemini vs google slug. The canonical provider slug is `gemini`, not `google`. It is the
`ProviderCredential.provider` value, the secret store slug (`secret://gemini`), the litellm prefix
(`gemini/`), and the `PROVIDER_ENV_FIELDS` key (`gemini -> gemini_api_key`). Using `gemini` rather
than `google` keeps the model provider account distinct from any future Google OAuth connector and
matches the litellm route. The UI labels it "Google (Gemini)".

Connect endpoint (Settings initiated, reusing the secret store and reference only discipline):
`POST /settings/providers/connect` accepts the key over the authenticated session only, calls
`store_secret`, upserts the `ProviderCredential` row (status `connected`, hint set), runs
`assert_no_secret` on the response view, and discovery is run on demand (section 4).
`POST /settings/providers/{provider}/disconnect` clears `credentials_ref` and `hint`, sets
`status="available"`, deletes the stored secret, and leaves discovered models in place but
unselectable (their provider is no longer connected). Managing provider credentials is limited to
owner and admin, reusing the `require_manager` gate from the users router. Tavily is a search tool,
not a litellm chat provider, so it is not in `KNOWN_PROVIDERS`; a Tavily key, if needed, is still
storable by provider slug through the same connect path and read by the research agent, never by the
chat router.

## 2. Router resolution order: store first, env fallback, explicit key to litellm

The router resolves the provider key at call time, in this order:

1. Determine the provider from the model id prefix: `anthropic/` -> `anthropic`, `openai/` ->
   `openai`, `gemini/` -> `gemini`. The Tavily path (used by the research agent, not litellm chat)
   resolves the `tavily` provider directly.
2. Secret store first: if `has_secret(provider)`, read it with a new server-only
   `read_secret(provider)` added to `secret_store.py`. This is the function the existing store
   docstring already anticipates ("the router that needs a provider key at call time reads it here
   on the server, never over HTTP"). It reads the file under `NEXA_SECRETS_ROOT` and returns the
   value to in-process callers only. It is never wired to a route and never returned in a response.
3. Environment fallback: if no stored secret exists, fall back to the matching
   `settings.<provider>_api_key`. This keeps a fresh checkout and the existing `.env` working with
   no migration of secrets required.
4. Pass the key explicitly to litellm: change `route_completion` (and the direct
   `litellm.completion` / `litellm.transcription` calls in `services/brain/app/routers/journal.py`)
   to pass `api_key=<resolved key>` rather than relying on litellm reading the environment. Explicit
   passing makes the store the source of truth, makes the env a true fallback, and avoids a
   process-wide env mutation. For Gemini, litellm accepts `api_key` for the Google AI Studio
   `gemini/` route; record that Vertex is out of scope for Phase 4.

Two helpers centralise this: `provider_of(model_id) -> str` extracts the provider prefix, and
`resolve_provider_key(provider) -> str | None` runs steps 2 and 3 (store first, then env). The
router, the journal routes, and the offline check all share them. `offline.py` `has_provider_keys`
reflects any provider resolvable from store or env, so the offline fallback honours connected
accounts, not just `.env`.

Caching: the file read is cheap, so the router reads per call by default. An optional in-process
cache keyed by provider may be added with explicit invalidation on connect and disconnect; it is not
required for correctness and is a later optimisation, not part of the contract.

## 3. The masked hint (last four, non-secret)

At write time only, the connect path computes a masked hint from the key with
`secret_store.mask_hint` and stores it on the `ProviderCredential` row in `hint`. Format: a `****`
prefix plus the last four characters, for example `****3xQk`. Four trailing characters of a long
opaque key are not sensitive and cannot reconstruct the key. The hint exists so the UI can show
"Connected" with a recognisable tail without ever reading the key back.

Rules:

- The hint is derived once, at the moment the key is stored, from the in-memory value. The stored
  key is never read to recompute it.
- The hint is the only key-derived value that ever crosses the API boundary. It is carried on
  `ProviderStatus` as the optional `hint` field. There is no endpoint that returns the full key.
- A key with no trailing characters degrades to a fixed `****` with no tail, so an empty or trivial
  key never leaks a meaningful fraction of itself.
- `hint` is not a secret-bearing field name, so the redaction guard allows it. The guard still runs
  on the connect response (`assert_no_secret(status.model_dump(), ...)`) as a backstop.

## 4. Discovery, cache shape, refresh, and the migration

Discovery is a server-side call per provider using the resolved key, run on connect and on an
explicit "Refresh models" action, and as a soft refresh past a TTL.

Per provider discovery call:

- Anthropic: `GET https://api.anthropic.com/v1/models` with headers `x-api-key: <key>` and
  `anthropic-version: 2023-06-01`. Returns the model ids the account can use.
- OpenAI: `GET https://api.openai.com/v1/models` with `Authorization: Bearer <key>`.
- Gemini (Google AI): `GET https://generativelanguage.googleapis.com/v1beta/models?key=<key>`.
  Returns models with supported methods, which we use to tag capabilities.
- Tavily: key only. Tavily is a search tool, not a chat model provider, so there is nothing to
  enumerate. Discovery validates the key with a minimal authenticated probe and, on success, records
  a single synthetic capability row (`tavily/search`, enabled) so the UI can show the account as
  connected and usable. A failed probe leaves the account connected by reference but flagged
  unverified.

litellm provider helpers may be used where convenient, but the explicit list endpoints above are the
contract so discovery does not depend on litellm's internal model registry. All calls read the key
from the store or env (section 2); the key never appears in the discovery results.

Cache shape (as built): the `discovered_models` table (`services/brain/app/models/provider.py`),
one row per discovered model:

- `id` (pk)
- `provider` (string, the canonical provider slug; scopes the row, no FK, indexed)
- `model_id` (string, the provider-prefixed canonical id, for example
  `anthropic/claude-sonnet-4-6`, built by `_canonical_id` so it matches what `models.yaml`
  references and can be auto enabled)
- `name` (string, the raw model name as the provider returned it, for display)
- `enabled` (boolean, default false; see section 5)
- `created_at` (datetime, from the timestamp mixin)

A `UniqueConstraint("provider", "model_id")` keeps discovery idempotent. Capabilities tagging, a
`last_seen_at` column, a `raw` audit blob, and per provider discovery metadata are deliberately out
of Phase 4 and noted here as later follow-ups; the built row carries only what the picker needs.

Refresh semantics (as built):

- A manual "Refresh models" control per provider (`POST /settings/providers/{provider}/refresh`)
  runs discovery. Connect does not auto-run discovery; refresh is the explicit trigger. (A soft TTL
  and a background refresh are a later follow-up, not Phase 4.)
- Re-discovery upserts by `(provider, model_id)`: a newly returned model is inserted (enabled per
  section 5); an existing row keeps the user's enable choice, except a referenced id is force
  enabled; a model the provider no longer returns is left in place, never deleted. This is additive,
  consistent with rule 12 on soft deletes.

Migration 0018 (additive only, per CLAUDE.md rule 7):

- `op.create_table("provider_credentials", ...)`: `id`, `provider`, `status`
  (`server_default="available"`), `credentials_ref`, `hint`, `created_at`, with a unique index on
  `provider`.
- `op.create_table("discovered_models", ...)`: `id`, `provider`, `model_id`, `name`
  (`server_default=""`), `enabled` (`server_default=sa.false()`), `created_at`, with a unique
  constraint on `(provider, model_id)` and an index on `provider`.
- Both are fresh `create_table` calls, which SQLite accepts, so no `batch_alter_table` is needed.
  Nothing existing is altered, and no key is ever stored in either table.

## 5. Enable and disable semantics

- Each `discovered_models` row has an `enabled` boolean. Disabled models are meant to be hidden from
  the remap picker and not selectable.
- Default on discovery is `enabled=false` (opt in), so connecting a busy account does not flood the
  picker with dozens of models.
- Auto-enable on first discovery (built): when discovery inserts a model whose canonical `model_id`
  is already referenced by a semantic key in `models.yaml` (for example `anthropic/claude-sonnet-4-6`,
  `openai/gpt-4o`, `openai/whisper-1`, `anthropic/claude-haiku-4-5-20251001`,
  `anthropic/claude-opus-4-8`), it is inserted with `enabled=true`, and an existing row for a
  referenced id is force enabled on refresh. This guarantees the current mappings stay valid the
  moment an account is connected, with no manual step. The referenced set is read from
  `model_router.load_config()` at discovery time (`discovery.referenced_model_ids`), so it always
  matches the live config.
- Enable and disable are explicit user actions in Settings (built):
  `PATCH /settings/providers/models/{model_id}` (the discovered model row id) with
  `{ "enabled": true|false }`, owner or admin only.
- Remap gating is a Phase 4 follow-up, not yet built. The intended rule: the remap endpoint
  (`PATCH /settings/models/keys/{key}` in `services/brain/app/routers/model_config.py`) and the add
  key endpoint will validate that `payload.model` is an `enabled` `discovered_models` row whose
  provider is currently connected (400 when unknown or not enabled, 409 when the provider is not
  connected), and a model a semantic key still maps to will not be disablable (409 naming the keys).
  The Models and Agents picker will list only enabled models. Until that lands, remap is unchanged
  and the auto-enable rule keeps the live mappings valid.

## 6. Redaction and the HTTPS gate

Redaction points (no key reaches a response, a log, or the runtime ledger):

- Response: `ProviderStatus` carries `provider`, `status`, `connected`, `source` (`store`, `env`, or
  null), and `hint` (non-secret). `DiscoveredModelRead` carries `id`, `provider`, `model_id`,
  `name`, `enabled`. Neither carries the key. There is no endpoint that returns a stored key, and
  `read_secret` and `resolve_provider_key` are server only, never bound to a route. A planted-key
  test (section below) greps the OpenAPI document and every provider read response for a distinctive
  key literal and asserts it never appears.
- Connect path: the connect handler runs `assert_no_secret` on the response view before returning,
  the same backstop the fulfil path uses. The inbound key is consumed straight into `store_secret`
  and is never copied onto any persisted object.
- Discovery: discovery returns only model ids; no key field is written to `discovered_models`. The
  discovery HTTP calls put the key only in a request header or query and never log it; a failure
  raises a sanitised `DiscoveryError` that names the provider, not the request.
- Logs: the key is never logged. litellm and the discovery client are configured so request logging
  does not echo the `api_key`, query key, or auth header. Provider errors are surfaced as sanitised
  messages (status and provider, not the request that carried the key).
- Runtime ledger: unchanged. Steps and evidence continue to carry only `secret://<provider>` or
  `credentials_ref`, never a value, enforced by `assert_no_secret` as today.

HTTPS gate for key entry (planned, a Phase 4 follow-up):

- The connect endpoint that accepts a key will require HTTPS, reusing the cookie-security logic in
  `services/brain/app/security/auth.py` (`_cookie_secure`): the request is allowed when
  `NEXA_PUBLIC_HTTPS` is true or the live request scheme is https. A plaintext http POST that
  carries a key is rejected with 400 (or 403) and a clear message, except on localhost dev where the
  same exemption that lets dev cookies work applies. This keeps a key from ever crossing the wire in
  cleartext in production while keeping local development usable. Today the connect endpoint is
  guarded by the authenticated owner or admin session; the explicit HTTPS rejection is the remaining
  follow-up.
- The gate applies only to the key-entry endpoint. Read and discovery endpoints carry no secret and
  are not gated beyond the normal authenticated session.

## Acceptance summary

This plan records:

- Storage decision: a dedicated, server wide `ProviderCredential` table (not the per user
  `Integration` row), with the reason recorded, plus the `discovered_models` cache and the `gemini`
  slug handling (section 1).
- Router resolution order: secret store first, environment fallback, key passed explicitly to
  litellm via `provider_of` plus `resolve_provider_key` and the server-only `read_secret` (section 2).
- The masked hint stored at write time, `****` plus the last four characters, non-secret, carried on
  `ProviderStatus` as `hint` (section 3).
- Discovery call per provider, the built `discovered_models` cache shape, the refresh semantics, and
  migration 0018 creating both tables with an `enabled` flag (section 4).
- Enable and disable rules, auto-enable on first discovery of models the semantic keys already
  reference, the built toggle endpoint, and the remap gating follow-up (section 5).
- Redaction points (response, connect, discovery, logs, ledger), a planted-key test over the OpenAPI
  and responses, and the HTTPS gate follow-up for key entry (section 6).
