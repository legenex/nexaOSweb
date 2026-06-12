# nexaOSweb Build Playbook
From an empty repo to a deployed Brain with Mac and Windows installers. Paste one prompt at a time into Claude Code, in order. Each prompt starts with its ID and name, then the CLAUDE.md and ARCHITECTURE.md reference. Close each prompt's acceptance criteria before advancing.

## Run order
Phase 0 then Phase 1 then Phase 2 are serial because each persists what the next reads. Phase 3 begins after F7 exists so the OpenAPI is stable. Phase 4 follows the web app. Phase 5 deploys once the Brain and web build cleanly. Anything touching models or migrations is serial. Stage by explicit path, one commit each.

---

## PHASE 0, foundation

```
P0.1: initialise the monorepo and commit the foundation docs
Following CLAUDE.md and docs/ARCHITECTURE.md. Initialise the repo at github.com/legenex/nexaOSweb. If it is empty, scaffold it. If it already has content, work alongside it without deleting anything.
- Create the pnpm workspace: package.json, pnpm-workspace.yaml covering apps/*, packages/*, and a root .gitignore that excludes node_modules, dist, .env, .venv, and build output.
- Create the folders services/brain, apps/web, apps/desktop, packages/api-client, docs, design.
- Add README.md describing the one frontend three targets design and the dev commands.
- Add CLAUDE.md, docs/ARCHITECTURE.md, and docs/FLOW_VISUAL_SPEC.md with the contents provided alongside this playbook. Add the provided design/flow_prototype_v4.html as the canonical visual reference.
Stage by explicit path. Commit: chore: initialise monorepo and foundation docs.
```

```
P0.2: shared tooling
Following CLAUDE.md and docs/ARCHITECTURE.md. Add base tooling without app code.
- Root tsconfig.base.json, eslint, and prettier configs. No em dash in any config comment.
- An EditorConfig.
- A docs/DEPLOY_PLESK.md placeholder that later prompts fill in.
- .github/workflows/ci.yml that installs and lints the web and packages, and runs the Brain lint and tests, on push and pull request.
Stage by explicit path. Commit: chore: shared tooling and ci skeleton.
```

---

## PHASE 1, Brain core

```
B1: scaffold the FastAPI Brain
Following CLAUDE.md and docs/ARCHITECTURE.md. Create services/brain as a Python project.
- pyproject.toml with FastAPI, uvicorn, SQLAlchemy, Alembic, pydantic-settings, psycopg, and python-multipart.
- app/main.py with the FastAPI app and CORS from CORS_ORIGINS. app/settings.py reading the environment variables listed in ARCHITECTURE.md, defaulting DATABASE_URL to a local SQLite file. app/db.py with the engine and session. app/models/base.py.
- GET /healthz returning ok. Alembic initialised against app metadata with an empty baseline migration.
- A Dockerfile running uvicorn, and a .env.example listing every variable with blank values.
Acceptance: uvicorn boots, /healthz returns ok, alembic upgrade head runs on a fresh SQLite db. Stage by explicit path. Commit: feat(brain): fastapi scaffold and health.
```

```
B2: auth and security for both clients
Following CLAUDE.md and docs/ARCHITECTURE.md. Add the User model and the two auth paths.
- User model and additive migration.
- POST /auth/login issues an httpOnly SameSite session cookie, Secure gated by NEXA_PUBLIC_HTTPS. POST /auth/logout, GET /auth/me, GET /auth/csrf for the double submit token. Login is rate limited.
- A dependency that accepts either a valid session plus CSRF on state changing requests, or a static bearer equal to NEXA_DESKTOP_BEARER for the desktop client.
- Passwords hashed. No secret is ever returned to the client.
Acceptance: a login sets the cookie, a bearer request authenticates, a state changing request without CSRF is rejected. Stage by explicit path. Commit: feat(brain): session and bearer auth with csrf.
```

```
B3: litellm model router
Following CLAUDE.md and docs/ARCHITECTURE.md. Add the multi provider router.
- config/models.yaml mapping the semantic keys general, agentic_code, research_synthesis, bulk, journal_reflection, vision to concrete models.
- app/router/model_router.py exposing model_for(key) and route_completion, plus sampling normalisation. app/json_extract.py with synthesize_json(key, prompt, schema) that returns parsed JSON.
- Provider keys are read only from the environment by the Brain. Business logic references keys, never model ids.
Acceptance: a unit test resolves each key, and synthesize_json parses a structured response from a mocked provider. Stage by explicit path. Commit: feat(brain): litellm model router and json synthesis.
```

```
B4: core data model
Following CLAUDE.md and docs/ARCHITECTURE.md. Add the entities from the data model section, additive only: InboxItem, ClassificationRecord, PipelineRun, Project, Integration, PMRun, Task, JournalNote, AppSetting. Include stage_history on InboxItem and plan_path, plan_json, build_destination, selected_integrations on Project. Write one Alembic migration off the current head. Add Pydantic schemas for each in app/schemas. Acceptance: alembic upgrade head and downgrade run cleanly. Stage by explicit path. Commit: feat(brain): core data model and schemas.
```

---

## PHASE 2, Flow pipeline

```
F1: capture endpoint
Following CLAUDE.md and docs/ARCHITECTURE.md. POST /intake/capture accepts multipart with a project name, a body, an optional file, and a source tag. It stores any file under NEXA_UPLOADS_ROOT through the path safety gate, creates one InboxItem at status captured, and returns it. Add GET /intake/items paginated and GET /intake/items/{id}. Reflect the OpenAPI. Stage by explicit path. Commit: feat(brain): intake capture and items.
```

```
F2: classifier and decision record
Following CLAUDE.md and docs/ARCHITECTURE.md. Add app/agents/classify.py that classifies an InboxItem into a shape (project, campaign, technical, gtd, content, private, park, archive) with a confidence, tags, a recommended route, and a model selection. Persist a ClassificationRecord including recommended_model_key, resolved_model_id from the router, model_rationale, and a plain reasoning_summary with no hidden chain of thought. Classify on ingest in the background, with a retry sweep on a schedule and a confidence threshold setting. Add GET /intake/items/{id}/classification. Reflect the OpenAPI. Stage by explicit path. Commit: feat(brain): classifier and decision record.
```

```
F3: router
Following CLAUDE.md and docs/ARCHITECTURE.md. Add app/agents/route.py. Project shaped items create a Project at stage idea. Task items attach to a get or create Inbox Tasks project. Journal items create a JournalNote. Private, park, campaign, technical, content, and archive resolve to their workflow state without deep processing. Items below the confidence threshold are escalated and stay in the inbox. Record each routing on PipelineRun and stage_history. Stage by explicit path. Commit: feat(brain): router across eight workflows.
```

```
F4: process stage
Following CLAUDE.md and docs/ARCHITECTURE.md. POST /flow/items/{id}/process for a project shaped item. Reuse the Project the router created. Create the folder under NEXA_PROJECTS_ROOT using the project slug through the path safety gate. Generate a structured plan via synthesize_json with the sections in the prototype (summary, objective, outcome, tree, workstreams, deliverables, subtasks, dependencies, assets, owners, open questions, risks, complexity, next steps, proposed build destination, likely integrations), render it to project_plan.md, and persist plan_path, plan_json, and build_destination on the Project. Add GET /flow/items/{id}/plan that streams the markdown. Does not activate the project. Reflect the OpenAPI. Stage by explicit path. Commit: feat(brain): process stage builds folder and plan.
```

```
F5: clarify stage
Following CLAUDE.md and docs/ARCHITECTURE.md. GET /flow/items/{id}/clarify returns gap closing questions from the plan and suggested integrations by intersecting the plan likely integrations with the user connected Integration rows. POST /flow/items/{id}/clarify accepts answers, selected integration ids, and scope changes, updates project_plan.md, writes change_summary.md, generates project_preview.html, and persists selected integrations and any build destination change. Add GET /flow/items/{id}/preview. All writes pass the path safety gate. Reflect the OpenAPI. Stage by explicit path. Commit: feat(brain): clarify with integrations and preview.
```

```
F6: human gate and execute
Following CLAUDE.md and docs/ARCHITECTURE.md. Add the project gate and the promote handoff.
- GET /projects, POST /projects/{id}/approve, POST /projects/{id}/reject.
- POST /flow/items/{id}/promote requires an approved project. It converts project_plan.md into requirements.md as the source of truth, hands off to a builder module that runs within the path safety gate and never force pushes protected branches, and creates a PMRun stub. The full project manager and specialist sub agents are deferred to a later milestone, note this in docs/ARCHITECTURE.md. Reflect the OpenAPI. Stage by explicit path. Commit: feat(brain): gate and execute promote handoff.
```

```
F7: flow aggregator and settings
Following CLAUDE.md and docs/ARCHITECTURE.md. Add GET /flow/items and GET /flow/items/{id} returning a single FlowItem DTO with capture meta, the classification record, the route, the linked project and stage, plan and preview availability, build destination, selected integrations, and the gate state. Add GET /settings and PATCH /settings for the intake knobs (confidence threshold, classify sweep enabled, interval, batch). Reflect the OpenAPI. This completes the v1 contract. Stage by explicit path. Commit: feat(brain): flow aggregator and settings.
```

---

## PHASE 3, web frontend

```
W0: scaffold the web app and design tokens
Following CLAUDE.md and docs/FLOW_VISUAL_SPEC.md. Scaffold apps/web with Vite, React, TypeScript, and Tailwind. Add a single tokens file holding every color and font as CSS variables per the visual spec. Build the app shell: the red sidebar with the nav from the visual spec and a main area with the holographic backdrop placeholder, a page title, and a mono section label. Add an auth layer that uses session cookies in the browser and reads a bearer when running in the desktop wrapper. Stage by explicit path. Commit: feat(web): app shell and design tokens.
```

```
W1: generate the typed api client
Following CLAUDE.md and docs/ARCHITECTURE.md. Add packages/api-client generated from the Brain OpenAPI, with a pnpm gen:client script at the root. Wire apps/web to call the Brain through this client with the base URL from an environment value, defaulting to the local Brain in dev and the hosted /api in production. Stage by explicit path. Commit: feat(client): generated api client and wiring.
```

```
W2: flow panorama shell
Following CLAUDE.md and docs/FLOW_VISUAL_SPEC.md. Build the Flow route as a horizontal deck of the seven stage cards. Add the shared primitives MonoLabel, StatusDot, StageTrack, GlassCard, Pill, and Button. Add the holographic rotating sphere on a canvas with requestAnimationFrame and a reduced motion fallback, and the curved connector wires in a layer behind the cards. Static placeholders, no data yet. Stage by explicit path. Commit: feat(web): flow panorama shell and primitives.
```

```
W3: interactive capture node
Following CLAUDE.md and docs/FLOW_VISUAL_SPEC.md. Build the Capture card as the interactive box: a drop target, a project name field, a description field, source chips, a Generate with AI button that calls the Brain to expand the description, a details modal, and a Capture button that posts to /intake/capture and starts the run. Stage by explicit path. Commit: feat(web): interactive capture node.
```

```
W4: classify and route nodes
Following CLAUDE.md and docs/FLOW_VISUAL_SPEC.md. Wire the Classify card to the classification record with a decision log modal and export, and the Route card to the eight workflows with the winning route lit and non project routes terminating. Read from /flow/items/{id}. Stage by explicit path. Commit: feat(web): classify and route nodes.
```

```
W5: process and clarify nodes
Following CLAUDE.md and docs/FLOW_VISUAL_SPEC.md. Wire the Process card with an open plan modal rendering the markdown, and the Clarify card with the questions, selectable integration chips, an open preview modal, and a continue action that posts the clarify answers. Stage by explicit path. Commit: feat(web): process and clarify nodes.
```

```
W6: gate, execute, and projects view
Following CLAUDE.md and docs/FLOW_VISUAL_SPEC.md. Wire the Human Gate card to approve and reject with links to plan and preview and a summary of integrations and build destination, the Execute card to promote with a worker list, and a Projects view that lists projects with the StageTrack and a fresh project appearing after a run. Stage by explicit path. Commit: feat(web): gate, execute, and projects.
```

```
W7: motion, accessibility, and performance
Following CLAUDE.md and docs/FLOW_VISUAL_SPEC.md. Final pass. Holographic card sheen, active stage glow, connector flow, a pulse reactive to stage history, full prefers reduced motion paths, keyboard and screen reader labels on every interactive node and modal, and a performance pass that keeps the sphere and wires smooth on a full deck. Stage by explicit path. Commit: feat(web): polish and accessibility.
```

---

## PHASE 4, desktop

```
D1: Tauri v2 wrapper
Following CLAUDE.md and docs/ARCHITECTURE.md. Scaffold apps/desktop as a Tauri v2 app that loads the built apps/web. Configure a frameless window with a custom titlebar matching the design, point the API base at the hosted Brain in production and the local Brain in dev, and store the desktop bearer in the OS secure store rather than the bundle. Add pnpm scripts for tauri dev and tauri build. Acceptance: tauri dev opens the app and reaches a local Brain. Stage by explicit path. Commit: feat(desktop): tauri v2 wrapper.
```

```
D2: dual OS installers in CI
Following CLAUDE.md and docs/ARCHITECTURE.md. Add .github/workflows/desktop-build.yml with a matrix that builds the Mac dmg on macOS and the Windows msi on Windows, signs each using secrets, and publishes the installers as release artifacts. Wire the Tauri updater so the apps can pull new versions. Document the signing secrets in docs/DEPLOY_PLESK.md. Stage by explicit path. Commit: ci(desktop): mac and windows installers.
```

---

## PHASE 5, ship to Plesk

```
S1: deploy the Brain on Plesk
Following CLAUDE.md and docs/ARCHITECTURE.md. Fill in docs/DEPLOY_PLESK.md with the production setup: the Brain as a Dockerized uvicorn service or a Plesk Python application behind the Plesk Nginx, a Postgres database, a server side .env holding every secret, alembic upgrade head on deploy, and a Let's Encrypt certificate. Add the Nginx location that proxies /api to the Brain. Acceptance: the documented steps bring /healthz up over HTTPS at the domain. Stage by explicit path. Commit: docs: plesk brain deploy.
```

```
S2: serve the web companion on Plesk
Following CLAUDE.md and docs/ARCHITECTURE.md. Document and configure building apps/web to static files served by the Plesk Nginx at the site root, with the API at /api. Turn on NEXA_PUBLIC_HTTPS so session cookies are Secure, confirm CSRF on state changing requests, and set CORS_ORIGINS to the domain. Acceptance: a browser login works end to end against the hosted Brain. Stage by explicit path. Commit: docs: plesk web companion.
```

```
S3: deploy pipeline
Following CLAUDE.md and docs/ARCHITECTURE.md. Add .github/workflows/deploy.yml that on a tagged release builds the web, ships the Brain and the web build to the Plesk server over ssh, runs migrations, and hits /healthz to verify. Keep all credentials in repository secrets. Stage by explicit path. Commit: ci: plesk deploy pipeline.
```

---

## After v1
Research, Tasks, and Journal tabs reuse the same pipeline and primitives and come next. The full project manager agent and the specialist sub agents (developer, researcher, market research, creative, technical, data, QA, operations, analytics) are a dedicated milestone after the Execute handoff proves out.
