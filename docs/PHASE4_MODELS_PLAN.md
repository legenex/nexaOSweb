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

## 1. Storage decision: reuse the Integration model

Decision: reuse the existing `Integration` model (`services/brain/app/models/project.py`) for
provider accounts. Do not add a dedicated provider table.

Why reuse:

- `Integration` already carries exactly the shape a provider account needs: `user_id`, `provider`,
  `status`, and `credentials_ref` (a reference into the secret store, never the raw secret). See
  `docs/ARCHITECTURE.md` line 61.
- The credential fulfil pattern already writes `Integration` rows by reference for arbitrary
  providers. `fulfil_credential_step` stores the secret with `store_secret(provider, secret)`,
  sets `status="connected"` and `credentials_ref=secret://<provider>`, and records only the
  reference on the ledger. A provider account connect is the same write with a different trigger
  (a Settings action instead of a readiness step).
- Readiness already treats a connected `Integration` as the only source that satisfies a credential
  item (`_resolve_credential`). Reusing the table means a connected provider account is visible to
  readiness with no extra wiring.
- The redaction guard, the secret store, and the reference-only discipline already cover this table.
  A second table would duplicate all of it.

Two small additive columns are needed on `integrations` (see the migration in section 4):

- `kind` (nullable string, default null): set to `model_provider` for a provider account, left null
  (or `connector`) for an OAuth or tool connector. This disambiguates a `gemini`/`google` model
  account from a Google connector and lets the Settings list filter cleanly. Identifying model
  providers by name alone is fragile because `google` is shared; the explicit kind removes the
  ambiguity.
- `secret_hint` (nullable string): the masked last four characters stored at write time (section 3).

A provider account row therefore looks like: `provider="anthropic"`, `kind="model_provider"`,
`status="connected"`, `credentials_ref="secret://anthropic"`, `secret_hint="...info-3xQk"`.

Connect endpoint (reusing the fulfil discipline, Settings initiated, no readiness step):
`POST /settings/models/providers/{provider}/connect` accepts the key over the authenticated session
only, calls `store_secret`, upserts the `Integration` row (kind `model_provider`, status
`connected`, hint set), runs `assert_no_secret` on the response model, and kicks off a first
discovery (section 4). `POST /settings/models/providers/{provider}/disconnect` clears
`credentials_ref` and `secret_hint`, sets `status="available"`, and leaves discovered models in
place but unselectable (their provider is no longer connected). Managing provider accounts is
limited to owner and admin, reusing the `require_manager` gate from the users router.

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

A thin helper, `resolve_provider_key(model_id) -> str | None`, centralises steps 1 to 3 so the
router, the journal routes, and the offline check all share one resolution. `offline.py`
`has_provider_keys` becomes "any provider resolvable from store or env" so the offline fallback
reflects connected accounts, not just `.env`.

Caching: the file read is cheap, so the router reads per call by default. An optional in-process
cache keyed by provider may be added with explicit invalidation on connect and disconnect; it is not
required for correctness and is a later optimisation, not part of the contract.

## 3. The masked hint (last four, non-secret)

At write time only, the connect path computes a masked hint from the key and stores it on the
`Integration` row in `secret_hint`. Format: an ellipsis prefix plus the last four characters, for
example `...3xQk`. Four trailing characters of a long opaque key are not sensitive and cannot
reconstruct the key. The hint exists so the UI can show "Connected" with a recognisable tail without
ever reading the key back.

Rules:

- The hint is derived once, at the moment the key is stored, from the in-memory value. The stored
  key is never read to recompute it.
- The hint is the only key-derived value that ever crosses the API boundary. It is carried on
  `IntegrationRead` as a new optional `secret_hint` field. There is no endpoint that returns the
  full key.
- If a key is shorter than eight characters the hint degrades to a fixed `...` with no tail, so a
  short or test key never leaks a meaningful fraction of itself.
- `secret_hint` is not a secret-bearing field name, so the redaction guard allows it. The guard
  still runs on the connect response as a backstop.

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

Cache shape: a new additive table `provider_models`, one row per discovered model:

- `id` (pk)
- `provider` (string, the canonical provider id; scopes the row, no FK needed since provider is a
  stable string key shared with `integrations.provider`)
- `model_id` (string, the provider-prefixed id litellm uses, for example `anthropic/claude-sonnet-4-6`)
- `display_name` (string, the human label from the provider, falling back to `model_id`)
- `capabilities` (JSON, for example `["chat"]`, `["chat","vision"]`, `["transcription"]`,
  `["embedding"]`, derived from the provider response so the picker can filter by what a key needs)
- `enabled` (boolean, default false; see section 5)
- `discovered_at` (datetime, first seen)
- `last_seen_at` (datetime, updated every discovery that still returns the model)
- `raw` (JSON, the trimmed provider record for audit; never contains a key)

A uniqueness rule on `(provider, model_id)` keeps discovery idempotent (enforced in the ORM and the
upsert, not necessarily a DB constraint, consistent with the SQLite-first rule). Per provider
discovery metadata (last refresh time, last error) is stored on the `Integration` row via a small
additive use of `status` plus a `last_discovery_at` column, or kept in the `provider_models`
aggregate; the plan records `last_discovery_at` as a nullable column on `integrations` so the UI can
show "models refreshed N ago" without a join.

Refresh semantics:

- On connect, run discovery once immediately.
- A manual "Refresh models" control per provider re-runs discovery.
- A soft TTL (24 hours) triggers a background refresh on next read; stale data is still served until
  the refresh completes.
- Re-discovery upserts by `(provider, model_id)`: a model still returned has its `last_seen_at`
  bumped; a newly returned model is inserted (enabled per section 5); a model no longer returned is
  kept (not deleted) and simply stops having its `last_seen_at` advanced, so the UI can show it as
  "no longer offered" rather than losing history. This is additive and soft, consistent with rule 12
  on soft deletes.

Migration (additive only, per CLAUDE.md rule 7):

- `op.create_table("provider_models", ...)` with the columns above. A fresh `create_table` is
  SQLite-safe, so no `batch_alter_table` is needed for the new table.
- `op.add_column("integrations", sa.Column("kind", sa.String(40), nullable=True))`.
- `op.add_column("integrations", sa.Column("secret_hint", sa.String(40), nullable=True))`.
- `op.add_column("integrations", sa.Column("last_discovery_at", sa.DateTime(timezone=True), nullable=True))`.
- No foreign key is added to `integrations` from `provider_models` (provider is a string scope key),
  so the SQLite constraint limitation in rule 7 does not apply. If a future FK is wanted it must go
  through `op.batch_alter_table` with a named constraint, or be enforced in the ORM only.

The discovered model rows and the `provider_models` table never store a key. The `raw` JSON is
trimmed to non-secret fields and passed through `assert_no_secret` before it is written.

## 5. Enable and disable semantics

- Each `provider_models` row has an `enabled` boolean. Disabled models are hidden from the remap
  picker and cannot be selected.
- Default on discovery is `enabled=false` (opt in), so connecting a busy account does not flood the
  picker with dozens of models.
- Auto-enable on first discovery: when discovery first inserts a model whose `model_id` is already
  referenced by a semantic key in `models.yaml` (for example `anthropic/claude-sonnet-4-6`,
  `openai/gpt-4o`, `openai/whisper-1`, `anthropic/claude-haiku-4-5-20251001`,
  `anthropic/claude-opus-4-8`), it is inserted with `enabled=true`. This guarantees the current
  mappings stay valid the moment an account is connected, with no manual step. The set of referenced
  ids is read from `model_router.load_config()` at discovery time, so it always matches the live
  config.
- Enable and disable are explicit user actions in Settings:
  `PATCH /settings/models/providers/{provider}/models/{model_id}` with `{ "enabled": true|false }`.
- A model currently mapped by a semantic key cannot be disabled. The disable request returns 409
  with a message naming the keys that use it, so the user must remap those keys first. This prevents
  a remap from silently pointing at a disabled model.
- Remap consumes only enabled models. The remap endpoint
  (`PATCH /settings/models/keys/{key}` in `services/brain/app/routers/model_config.py`) gains a
  validation step: `payload.model` must be an `enabled` row in `provider_models` whose provider is
  currently connected. Otherwise it returns 400 (unknown or not enabled) or 409 (provider not
  connected). The "add key" endpoint applies the same check. The Models and Agents picker in the web
  app lists only enabled models, grouped by provider, so the happy path cannot select a disabled or
  unconnected model.

## 6. Redaction and the HTTPS gate

Redaction points (no key reaches a response, a log, or the runtime ledger):

- Response: `IntegrationRead` carries `provider`, `status`, `credentials_ref` (a reference),
  `secret_hint` (non-secret), and `last_discovery_at`. It never carries the key. There is no
  endpoint that returns a stored key. `read_secret` is server only and is never bound to a route.
- Connect path: the connect handler runs `assert_no_secret` on the response model before returning,
  the same backstop the fulfil path uses. The inbound key is consumed straight into `store_secret`
  and is never copied onto any persisted object.
- Discovery: discovery results and the `provider_models.raw` JSON are passed through
  `assert_no_secret` before they are written, and the discovery HTTP calls are constructed so the key
  is only ever in the request header or query and never logged.
- Logs: the key is never logged. litellm and the discovery client are configured so request logging
  does not echo the `api_key`, query key, or auth header. Provider errors are surfaced as sanitised
  messages (status and provider, not the request that carried the key).
- Runtime ledger: unchanged. Steps and evidence continue to carry only `secret://<provider>` or
  `credentials_ref`, never a value, enforced by `assert_no_secret` as today.

HTTPS gate for key entry:

- The connect endpoint that accepts a key requires HTTPS. It reuses the cookie-security logic in
  `services/brain/app/security/auth.py` (`_cookie_secure`): the request is allowed when
  `NEXA_PUBLIC_HTTPS` is true or the live request scheme is https. A plaintext http POST that
  carries a key is rejected with 400 (or 403) and a clear message, except on localhost dev where the
  same exemption that lets dev cookies work applies. This keeps a key from ever crossing the wire in
  cleartext in production while keeping local development usable.
- The gate applies only to the key-entry endpoint. Read and discovery endpoints carry no secret and
  are not gated beyond the normal authenticated session.

## Acceptance summary

This plan records:

- Storage decision: reuse `Integration` with additive `kind`, `secret_hint`, and
  `last_discovery_at` columns, and why a dedicated table is not used (section 1).
- Router resolution order: secret store first, environment fallback, key passed explicitly to
  litellm via a shared `resolve_provider_key` helper and a new server-only `read_secret` (section 2).
- The masked hint stored at write time, last four characters only, non-secret, carried on
  `IntegrationRead` (section 3).
- Discovery call per provider, the `provider_models` cache shape, the refresh and TTL semantics, and
  the additive migration for discovered models with an `enabled` flag (section 4).
- Enable and disable rules, auto-enable on first discovery of models the semantic keys already
  reference, and remap consuming only enabled, connected models (section 5).
- Redaction points (response, connect, discovery, logs, ledger) and the HTTPS gate for key entry
  (section 6).
