# READ FIRST: NexaOS project guardrail

Upload this as a project file in the Claude.ai NexaOS project. It replaces the older guardrail
that described a native SwiftUI app. The build is web first.

## What NexaOS is
A web first personal AI operating system. Two pillars joined by a decide layer:
- Build pillar: the seven stage Flow pipeline (Capture, Classify, Route, Process, Clarify, Human
  Gate, Execute), shown in the UI as Project Builder. Internal name stays Flow.
- Learn pillar: a nightly Dreaming consolidation that extracts memory candidates and, on explicit
  approval, writes them into the Knowledge base.
- Decide layer: Focus ranks work from the Knowledge base. Surfaced view ships later.

## Stack (do not deviate without a recorded decision in docs/ARCHITECTURE.md)
- Brain: Python FastAPI, SQLAlchemy, Alembic, Postgres in prod and SQLite in dev, litellm router.
- Frontend: React, Vite, TypeScript, Tailwind. Generated client in packages/api-client.
- Desktop: Tauri v2 wrapping the same web build (Mac dmg, Windows msi).
- Hosting: Plesk on a Linux VPS, Nginx, Let's Encrypt.

## Non negotiables
1. CLAUDE.md is the source of truth. Read it and the docs, and inspect HEAD, before any change.
2. No em dashes. Orange is the only brand color, all colors and fonts from CSS variables.
3. One commit per logical concern, staged by explicit path, conventional messages. Never git add -A.
4. Migrations are additive only. Constraint or FK changes use op.batch_alter_table with a named
   constraint, or omit the DB constraint and enforce it in the ORM and router.
5. The model is selected by semantic key from config/models.yaml, never a hardcoded model id.
6. Provider secrets live only in the server side .env. The apps never hold keys.
7. Destructive endpoints soft delete by default and stay recoverable. Hard delete is never default.
8. Verify before done: web typecheck, lint, build; Brain tests and a live check.

## How prompts run
Combine prompts when safe and say which run together. Above each prompt name, note "Runs with:
<ids>" or "Run alone". Batch independent prompts (no shared files, no migration or model ordering
conflict); keep migration and model or config prompts serial. Close acceptance criteria before
advancing.

## Surfaces
Sidebar order: Dashboard, Insights, Journal, Tasks, Research, Focus, Project Builder, Projects,
Settings. Settings sub tabs: General, Users, Integrations, Knowledge, Skills and Connectors,
Models and Agents, System. Capture lives in a global command bar (Ask Nexa) in the sidebar.
