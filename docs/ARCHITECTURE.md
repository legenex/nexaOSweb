# nexaOSweb Architecture
The decisions, the shape of the system, and the contracts. Read with CLAUDE.md.

## Two pillar model and the decide layer
NexaOS has two pillars joined by a decide layer. The Build pillar turns ideas into maintained projects. The Learn pillar turns lived activity into approved knowledge. The decide layer uses that knowledge to rank what to work on. This is a recorded decision and it does not change the stack. The Build pillar ships today. The Learn pillar and the decide layer are recorded now and built in later milestones, additive to the existing system.

- Build pillar. The seven stage Flow pipeline (Capture, Classify, Route, Process, Clarify, Human Gate, Execute) takes a captured idea and produces a maintained project. The pipeline is unchanged. In the user interface it is presented as Project Builder, while the internal pipeline name, the API paths, and the code stay Flow.
- Learn pillar. A nightly Dreaming consolidation reads the day's items and extracts memory candidates, both about the user and about the system itself. It writes approved candidates into a Knowledge base. No candidate enters long term memory without explicit user approval. Dreaming proposes, the user approves, and only then does a candidate become durable knowledge.
- Decide layer. Focus ranks work using the Knowledge base, joining the two pillars so that what the system learned shapes what it asks the user to do next. The surfaced view (Surface) ships in a later milestone. The intent is recorded now so the pillars are designed against it.

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
- Canonical sidebar order, top to bottom: Dashboard, Insights, Journal, Tasks, Research, Focus, Project Builder, Projects, Settings. Dashboard is the default landing route. A global command bar sits above the sidebar and owns Capture. Focus is the decide layer and ships later, shown as a placeholder until Surface lands.
- Settings sub tabs, in order: General, Users, Integrations, Knowledge, Skills and Connectors, Models and Agents, System.
- Knowledge is a Settings sub tab, not a top level sidebar item. The Learn pillar surfaces here. Inside Knowledge the internal tabs are General, Personal, Development, API connections, Dreaming. The memory candidate review and approval queue lives in Settings, Knowledge, Dreaming, where the user approves or rejects Dreaming candidates before they become durable, and the same queue is surfaced on the Dashboard as the Dream Digest. There is no Memory settings tab.

## Deferred milestone, project manager and specialist agents
The Execute stage currently writes requirements.md as the source of truth, hands off to the builder within the path safety gate, and records a PMRun stub. The full project manager agent and the specialist sub agents (developer, researcher, market research, creative, technical, data, QA, operations, analytics) are a dedicated later milestone after the Execute handoff proves out. They are intentionally not built in F6.

## Agent runtime (the spine the executor will drive)
The runtime is the durable ledger of what an agent intended, did, and proved. It exists before the executor so the executor has truth to write into, and so the honesty rules are enforced by the data layer rather than by the agent that will later run on top of it. Two tables only.
- AgentRun is the per run header: project_id (nullable), a cached status, an integer autonomy_level (the full 0 to 4 range is stored and only the binary is honored now, where 0 gates every step at waiting_approval and non-zero does not force the gate; the prompt 8 safe set check refines the non-zero branch later), the plan (json), goal_summary, context_summary, schema_version, and proposed_by. branch_ref and cursor_step_id are seams for the future executor and resume path and carry no logic yet; cursor_step_id has no DB level foreign key to avoid a circular constraint with agent_steps, so the relationship is enforced in the app. parent_run_id and pm_run_id are nullable seams for multi run handoff and the project manager link.
- AgentStep is the ordered ledger, indexed on (run_id, seq). Its fields are partitioned across four writers with no shared write path, so no single function authors a step end to end:
  - propose_step authors intent only (kind, title, intent, payload, proposed_by) and owns the entry gate (planned, or waiting_approval at autonomy 0). It has no parameter for status, outcome, evidence, or approval.
  - record_execution authors outcome, evidence, tool_call, and failure. It derives the terminal status from the work: a completed step is completed_verified only when its evidence carries at least one tool sourced item, otherwise completed_unverified. A verified status is never accepted as a target, and a terminal step cannot be mutated here.
  - resolve_approval owns only the approval exit edges: approve moves waiting_approval to planned, reject moves it to skipped. It writes only the approval resolution.
  - correct_step is the only writer that may change a terminal status. It records corrected_from and a required correction note and touches nothing else, and it can never set the derived completed_verified.

Principle enforcement. completed_verified is earned, never asserted: it is reachable only from executing and only with tool sourced evidence, and there is no code path, in process or over HTTP, that sets it directly. The eight step states (planned, waiting_approval, blocked, executing, completed_verified, completed_unverified, failed, skipped) move only along a single transition table the writers consult; there is no transition framework. failed is terminal except through the named correction or a future resume. The cached AgentRun.status is a pure derivation of its step statuses, refreshed after every writer call, and a test asserts the cache equals the derivation. Large tool output is not inlined: evidence over a size threshold spills to a file under NEXA_RUNTIME_ROOT and is kept in the row only by content_ref, with a byte count and a short preview. The /runtime surface is read only by design (a run with its steps, steps after a cursor, approval candidates, failed steps, proof of work per step, runs per project, the active runs, and per status counts); a test proves no runtime route accepts a mutating method, so no protected field is writable over the wire.

## Agent Build Engine
The Agent Build Engine is the layer that turns an approved project into built code by driving external coding agents. It sits downstream of Execute: Execute writes requirements.md as the source of truth and records the PMRun stub, then the engine consumes that project's requirements and its tasks and runs a coding agent to build it. It reuses the existing runtime spine rather than introducing a second run model. An engine run is an AgentRun of the executor kind, its plan and edits are AgentSteps, and the honesty and gating rules of the runtime hold unchanged.

A common AgentBackend adapter wraps each external coding CLI behind one interface, so the orchestrator drives any backend the same way (open a workspace, propose a change, return a diff). The backends are Claude Code (the default), Codex CLI (the second), and Grok Build (optional, feature flagged off by default). The backend is a config and adapter choice, never a hardcoded branch in business logic, in the same spirit as the model router.

Where runs execute. Engine runs execute on a dedicated build worker, never on the Plesk Brain. The Brain orchestrates, records the ledger, and serves the read only runtime surface; the worker is where the agent CLIs and the worktree edits actually run. This keeps the public web host free of agent execution and provider tooling.

Every change is gated. The agent proposes a diff and a deterministic gate, not the agent, commits or rejects it. The agent never writes to the served project folder directly: it edits only inside an isolated git worktree under NEXA_RUNTIME_ROOT through the path safety gate, the protected branch guard refuses protected branches, and the dangerous command guard wraps the git commands. Nothing leaves the worktree until the human approval gate is approved. This is the existing executor discipline (propose, check, diff, gate, merge, rollback), now driven by an external agent rather than the internal editor.

Secrets and the frozen core. Provider keys are server side only and never enter an agent prompt; the agent is given the task and the workspace, never a key. NexaOS's own orchestrator and safety code (the runtime writers, the gates, the safety gate, the engine itself) are frozen against agent modification by a path allowlist: the agent may write only within the project workspace, and a write that targets the engine's own source is refused.

This milestone proves a single gated run end to end on one backend. The full multi specialist project manager (the developer, researcher, QA, and other specialist sub agents described under the deferred milestone above) remains a later expansion and is intentionally not built here.

Reconciled in AB2.1 (single gated build run on the executor spine, proven in dev). One agent execution root: the AB1.1 sandbox (formerly NEXA_BUILDS_ROOT) is collapsed onto NEXA_RUNTIME_ROOT, so the engine workspace and the executor worktrees share one ensure_within_root boundary rather than two parallel sandbox systems, and a build run edits directly inside the executor's worktree. A build run is an AgentRun of the executor kind discriminated by a non-null backend column (with reasoning_summary, cost_usd, and a task_id link), so compute_diff_step, request_approval, merge_on_approval, and rollback_executor_run are reused unchanged. The run is dispatched through the in-process worker, which is correct for proving the loop in dev; the production build-worker host (a dedicated worker or container off the Plesk Brain, dispatched through a queue) is a deferred follow-up and is intentionally not solved here. The claude-code backend reports available only where the Claude Code CLI is installed and ANTHROPIC_API_KEY is set, which in dev is the Codespace; agent execution is never installed or assumed on the Plesk Brain.

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
- Project: id, item_id, name, slug, stage, plan_path, plan_json (json), build_destination, selected_integrations (json), research_target_id (self-referential, the build project a research project feeds, nullable, no DB level FK on the SQLite dev target), created_at.
- Integration: id, user_id, provider, status, credentials_ref. No raw secrets in the row, only a reference.
- PMRun: id, project_id, status, created_at. Stub for the future project manager interface.
- ProjectUpdate: id, project_id, kind (research_finding, manual, system), title, body, source_ref (json), created_at. The project Update Log.
- ResearchRun: id, project_id, status, summary, findings_count, finished_at, created_at.
- ResearchFinding: id, project_id, run_id, title, detail, url, status (new, tasked, logged, saved), created_at.
- AgentRun: id, project_id (nullable), status (cached, derived from steps), autonomy_level (int 0 to 4), branch_ref (seam, no logic), cursor_step_id (seam, no DB level FK), plan (json), goal_summary, context_summary, schema_version, proposed_by, parent_run_id (self-referential seam), pm_run_id (seam), created_at, updated_at, finished_at.
- AgentStep: id, run_id, seq, status (one of eight), kind, title, intent, payload (json), proposed_by, outcome, evidence (json), tool_call (json), failure (json), approval (json), correction_note, corrected_from, created_at, updated_at. Indexed on (run_id, seq). Authored only through the four runtime writers, see the Agent runtime section.
- Task, JournalNote, AppSetting: present from the data layer so the other tabs can grow later. AppSetting also holds the intake knobs, the knowledge policy, and the per day per mode dashboard brief cache, keyed per user.

## API surface (v1)
- Auth: POST /auth/login, POST /auth/logout, GET /auth/me, GET /auth/csrf.
- Intake: POST /intake/capture, GET /intake/items, GET /intake/items/{id}, GET /intake/items/{id}/classification.
- Flow: POST /flow/items/{id}/process, GET /flow/items/{id}/plan, GET /flow/items/{id}/clarify, POST /flow/items/{id}/clarify, GET /flow/items/{id}/preview, POST /flow/items/{id}/promote, GET /flow/items, GET /flow/items/{id}.
- Projects: GET /projects, POST /projects/{id}/approve, POST /projects/{id}/reject, GET /projects/{id}/updates (the project Update Log).
- Research: POST /research/{id}/attach, POST /research/{id}/detach, POST /research/{id}/runs, GET /research/{id}/runs, GET /research/{id}/findings, POST /research/findings/{id}/to-task, POST /research/findings/{id}/to-update, POST /research/findings/{id}/to-knowledge.
- Dashboard: GET /dashboard/summary, GET /dashboard/brief.
- Settings: GET /settings, PATCH /settings (intake knobs), GET /settings/knowledge-policy, PATCH /settings/knowledge-policy (ingestion and long term memory policy).
- Runtime (read only): GET /runtime/runs (filterable by project_id and active), GET /runtime/runs/{id} (run with steps), GET /runtime/runs/{id}/steps (after a cursor), GET /runtime/runs/{id}/approvals, GET /runtime/runs/{id}/failed, GET /runtime/runs/{id}/status-counts, GET /runtime/steps/{id}/proof. The ledger is authored only by the in-process writers, never over HTTP.
- Also shipped, see the OpenAPI for the full request and response shapes: Knowledge CRUD under /knowledge, the Dreaming review queue under /dreaming, Models and Agents under /settings/models, and System health and restart under /system.
- Health: GET /healthz.
The OpenAPI is the contract. After any change, regenerate packages/api-client.

## Dashboard summary and brief
The Dashboard is the cockpit. Two read endpoints back it.
- GET /dashboard/summary returns the Command Radar aggregate: counts and short lists for active projects, builds awaiting approval at the human gate, research findings ready to convert, suggested tasks, a top opportunity, recent uploads, connector health, model usage, and Brain status. It is read only.
- GET /dashboard/brief returns a time aware narrative. The mode is morning or evening; without an explicit ?mode= the Brain picks it from the time of day (evening from 17:00 on). Morning sets the day, evening reviews the day and sets tomorrow. The final text is written with the research_synthesis semantic key over a bulk key pre summarisation, and falls back to a deterministic offline rendering when no provider key is set. The brief is cached per day and per mode in an AppSetting row, so opening the Dashboard does not regenerate it. Pass ?refresh=true to force regeneration. The response carries mode, date, generated_at, cached, and text.

Two values behind these endpoints are deterministic proxies, not finished logic. Each has a named swap point. Do not mistake them for the real ranking.
- Research ready to convert currently proxies as classified InboxItems that have not yet become a project (dashboard._research_findings). Swap point: now that the research link exists, this becomes a real query over ResearchFinding rows with status new that belong to a research project.
- Top opportunity currently proxies as a deterministic heuristic over the gate, the findings, and the active projects (dashboard._top_opportunity). Swap point: it graduates to a ranked output when Focus, the decide layer, is built.

## Knowledge policy
GET and PATCH /settings/knowledge-policy hold what the system may ingest (ChatGPT via API, Claude via API, connectors) and what is allowed into long term memory (require approval, allow Dreaming memory, allow connector memory, and a minimum confidence). It is stored per user in an AppSetting row. The default keeps the human gate closed: ingestion off, memory_require_approval true, connector memory off, minimum confidence 0.6. Nothing reaches the Knowledge base without an explicit accept in the Dreaming review queue.

## Research link
A research project is an ordinary Project row, attached to a build project through the self-referential Project.research_target_id (nullable, additive). The DB level foreign key is omitted on purpose because SQLite cannot ALTER a constraint into an existing table; the ORM declares the relationship and the router validates the target exists.
- POST /research/{id}/attach and POST /research/{id}/detach set or clear the link. A research project cannot attach to itself.
- POST /research/{id}/runs triggers a run. GET /research/{id}/runs and GET /research/{id}/findings read the runs and their findings. A finding is new, tasked, logged, or saved.
- Finding level actions: POST /research/findings/{id}/to-task creates a Task on the attached build project (or on the research project itself when unattached); POST /research/findings/{id}/to-update posts a ProjectUpdate into the attached build project's Update Log, returning 409 when the research project is unattached; POST /research/findings/{id}/to-knowledge saves a KnowledgeEntry.
- GET /projects/{id}/updates reads a project's Update Log, the ProjectUpdate rows. When a run completes against an attached research project, its findings post into the target build project's Update Log.
- A finding saved to knowledge records source connector (not manual and not dreaming), with provenance {from: research_finding, finding_id, research_project_id, url}, so the origin stays traceable.

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
DATABASE_URL, NEXA_SESSION_SECRET, NEXA_PUBLIC_HTTPS, NEXA_DESKTOP_BEARER, NEXA_PROJECTS_ROOT, NEXA_UPLOADS_ROOT, NEXA_RUNTIME_ROOT (where large runtime tool output is stored by reference), CORS_ORIGINS, and the provider keys ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, TAVILY_API_KEY. Provider keys are read only by the Brain.
