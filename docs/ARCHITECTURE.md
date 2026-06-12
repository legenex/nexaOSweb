# nexaOSweb Architecture
The decisions, the shape of the system, and the contracts. Read with CLAUDE.md.

## Two pillar model and the decide layer
NexaOS has two pillars joined by a decide layer. The Build pillar turns ideas into maintained projects. The Learn pillar turns lived activity into approved knowledge. The decide layer uses that knowledge to rank what to work on. This is a recorded decision and it does not change the stack. The Build pillar ships today. The Learn pillar and the decide layer are recorded now and built in later milestones, additive to the existing system.

- Build pillar. The seven stage Flow pipeline (Capture, Classify, Route, Process, Clarify, Human Gate, Execute) takes a captured idea and produces a maintained project. The pipeline is unchanged. In the user interface it is presented as Project Builder, while the internal pipeline name, the API paths, and the code stay Flow.
- Learn pillar. A nightly Dreaming consolidation reads the day's items and extracts memory candidates, both about the user and about the system itself. It writes approved candidates into a Knowledge base. No candidate enters long term memory without explicit user approval. Dreaming proposes, the user approves, and only then does a candidate become durable knowledge.
- Decide layer. Focus and Accountability ranks work using the Knowledge base, joining the two pillars so that what the system learned shapes what it asks the user to do next. The surfaced view (Surface) ships in a later milestone. The intent is recorded now so the pillars are designed against it.

## Decisions and why
- One web frontend, three targets. A single React app is served by Plesk as the browser companion and wrapped by Tauri into Mac and Windows apps. This avoids maintaining separate native codebases and matches the holographic canvas style already prototyped.
- Tauri v2 over Electron for small binaries, a native webview, first class Mac and Windows support, and a clean updater. Electron is the only fallback if Rust or code signing friction becomes blocking.
- Python FastAPI Brain because litellm is the strongest multi provider router and is Python, the agent ecosystem is richest in Python, and Plesk runs Python cleanly. Type safety across the boundary is preserved by generating a TypeScript client from the OpenAPI.
- Postgres in production, SQLite in local dev, through the same SQLAlchemy models and Alembic migrations.

## System shape
Captured input becomes an InboxItem. The classifier writes a ClassificationRecord and selects a model by semantic key. The router sends project shaped items into Process, which creates a project folder and a draft plan. Clarify refines the plan, matches integrations, and renders a preview. The Human Gate approves, sends back, or archives. Execute promotes the plan to a requirements document and hands off to the builder, then a project manager interface maintains the project. Non project items terminate in their own workflow at Route. This pipeline is the Build pillar, shown in the interface as Project Builder.

## Navigation and information architecture
The interface is organized around the two pillars and the decide layer, not around the old inbox centric tabs.

- Flow is renamed to Project Builder in the user interface. The internal pipeline name, the API paths, and the code remain Flow. The rename is presentation only.
- Inbox and Reminders are removed as top level tabs. Capture moves into a global command bar that is available everywhere, and into the Project Builder capture stage. Reminders fold into Tasks.
- Canonical sidebar order, top to bottom: Dashboard, Insights, Journal, Tasks, Research, Focus and Accountability, Project Builder, Projects, Settings. Dashboard is the default landing route. A global command bar sits above the sidebar and owns Capture. Focus and Accountability is the decide layer and ships later, shown as a placeholder until Surface lands.
- Settings sub tabs, in order: General, Users, Integrations, Knowledge, Skills and Connectors, Models and Agents, System.
- Knowledge is a Settings sub tab, not a top level sidebar item. The Learn pillar surfaces here. Inside Knowledge the internal tabs are General, Personal, Development, API connections, Dreaming. The memory candidate review and approval queue lives in Settings, Knowledge, Dreaming, where the user approves or rejects Dreaming candidates before they become durable, and the same queue is surfaced on the Dashboard as the Dream Digest. There is no Memory settings tab.

## Deferred milestone, project manager and specialist agents
The Execute stage currently writes requirements.md as the source of truth, hands off to the builder within the path safety gate, and records a PMRun stub. The full project manager agent and the specialist sub agents (developer, researcher, market research, creative, technical, data, QA, operations, analytics) are a dedicated later milestone after the Execute handoff proves out. They are intentionally not built in F6.

## Repo layout
nexaOSweb/
  CLAUDE.md
  README.md
  package.json, pnpm-workspace.yaml
  docs/ ARCHITECTURE.md, FLOW_VISUAL_SPEC.md, DEPLOY_PLESK.md, BUILD_PLAYBOOK.md
  services/brain/ app/, config/, migrations/, pyproject.toml, Dockerfile
  apps/web/ src/, index.html, vite.config.ts, tailwind config
  apps/desktop/ src-tauri/, tauri.conf.json
  packages/api-client/ generated client
  .github/workflows/ ci.yml, desktop-build.yml, deploy.yml

## Data model (additive only)
- User: id, email, password hash, created_at.
- InboxItem: id, user_id, name, body, source, status, created_at, stage_history (json).
- ClassificationRecord: id, item_id, shape, confidence, recommended_route, recommended_model_key, resolved_model_id, model_rationale, reasoning_summary, tags (json), created_at.
- PipelineRun: id, item_id, stage, state, started_at, finished_at.
- Project: id, item_id, name, slug, stage, plan_path, plan_json (json), build_destination, selected_integrations (json), created_at.
- Integration: id, user_id, provider, status, credentials_ref. No raw secrets in the row, only a reference.
- PMRun: id, project_id, status, created_at. Stub for the future project manager interface.
- Task, JournalNote, AppSetting: present from the data layer so the other tabs can grow later.

## API surface (v1)
- Auth: POST /auth/login, POST /auth/logout, GET /auth/me, GET /auth/csrf.
- Intake: POST /intake/capture, GET /intake/items, GET /intake/items/{id}, GET /intake/items/{id}/classification.
- Flow: POST /flow/items/{id}/process, GET /flow/items/{id}/plan, GET /flow/items/{id}/clarify, POST /flow/items/{id}/clarify, GET /flow/items/{id}/preview, POST /flow/items/{id}/promote, GET /flow/items, GET /flow/items/{id}.
- Projects: GET /projects, POST /projects/{id}/approve, POST /projects/{id}/reject.
- Settings: GET /settings, PATCH /settings.
- Health: GET /healthz.
The OpenAPI is the contract. After any change, regenerate packages/api-client.

## Auth model
- Desktop: a static bearer token in the Authorization header, stored in the OS secure store, never in the bundle. Set as NEXA_DESKTOP_BEARER on the server.
- Web companion: login issues an httpOnly SameSite session cookie. State changing requests carry a CSRF token (double submit). Login is rate limited. NEXA_PUBLIC_HTTPS gates Secure cookies for local versus production.

## Model router
services/brain/config/models.yaml maps semantic keys to concrete models. The router exposes model_for(key) and route_completion. synthesize_json wraps a structured JSON generation. Business logic references keys only.

## Hosting on Plesk
The Brain runs as a Dockerized uvicorn service, or as a Plesk Python application via Passenger, behind the Plesk Nginx with a Let's Encrypt certificate. Nginx proxies /api to the Brain and serves the built apps/web at the site root. Postgres runs on the server. Secrets live in a server side .env that is never committed. Alembic upgrade head runs on deploy.

## Desktop build
apps/desktop is Tauri v2 pointing at the built apps/web. A GitHub Actions matrix builds the Mac dmg on macOS and the Windows msi on Windows, signs each, and publishes the installers. The Tauri updater can pull new versions.

## Environment variables
DATABASE_URL, NEXA_SESSION_SECRET, NEXA_PUBLIC_HTTPS, NEXA_DESKTOP_BEARER, NEXA_PROJECTS_ROOT, NEXA_UPLOADS_ROOT, CORS_ORIGINS, and the provider keys ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, TAVILY_API_KEY. Provider keys are read only by the Brain.
