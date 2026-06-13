# CLAUDE.md
House rules and project memory for nexaOSweb. Claude Code reads this first on every prompt. It is the authoritative source of truth for this repo.

## What this is
nexaOSweb is a personal AI operating system built on two pillars joined by a decide layer. The Build pillar is the existing seven stage Flow pipeline (Capture, Classify, Route, Process, Clarify, Human Gate, Execute) that turns a captured idea into a maintained project; in the user interface it is called Project Builder while the internal pipeline name stays Flow. The Learn pillar is a nightly Dreaming consolidation that reads the day's items, extracts memory candidates about the user and about the system itself, and writes approved candidates into a Knowledge base; no candidate enters long term memory without explicit user approval. The decide layer, Focus, ranks work using the Knowledge base, and its surfaced view ships later. One web frontend serves three targets: a browser companion hosted on Plesk, a Mac app, and a Windows app, both wrapped with Tauri. See docs/ARCHITECTURE.md for the full record.

## Stack (do not deviate without a recorded decision in docs/ARCHITECTURE.md)
- Backend Brain: Python FastAPI, SQLAlchemy, Alembic, Postgres in production and SQLite for local dev, litellm as the multi provider model router.
- Frontend: React, Vite, TypeScript, Tailwind. The holographic Flow panorama.
- Typed API client: generated from the Brain OpenAPI into packages/api-client.
- Desktop: Tauri v2 wrapping the same web build, producing a Mac dmg and a Windows msi.
- Hosting: Plesk on a Linux VPS, Nginx reverse proxy, Let's Encrypt SSL. Morne owns the server.

## Repo layout
- services/brain: the FastAPI Brain.
- apps/web: the React frontend.
- apps/desktop: the Tauri wrapper.
- packages/api-client: generated TypeScript client.
- docs: ARCHITECTURE.md, FLOW_VISUAL_SPEC.md, DEPLOY_PLESK.md.
- .github/workflows: ci, desktop installers, deploy.
- Root is a pnpm workspace. The Brain is a Python project under services/brain with its own pyproject.toml.

## Hard rules
1. No em dashes anywhere, in output or in code comments. Use commas, periods, or parentheses.
2. Complete files only. When changing a file, output the whole file, never a patch or diff.
3. One commit per logical concern. Stage by explicit path with git add <path>. Never git add -A.
4. Conventional commit messages, for example feat(brain): capture endpoint.
5. US market only in business logic.
6. The apps never hold provider secrets. All LLM and provider keys live only in the server side .env read by the Brain. The desktop app authenticates with a bearer token kept in the OS secure store. The web companion authenticates with httpOnly SameSite session cookies plus CSRF double submit, with an NEXA_PUBLIC_HTTPS flag for local versus production.
7. Database migrations are additive only. Add columns and tables, do not rewrite or destroy existing ones. Any migration that adds or alters a foreign key or other constraint must use op.batch_alter_table with a named constraint, because the dev target is SQLite (which cannot ALTER a constraint into an existing table) even though production is Postgres. If a foreign key cannot be added this way, omit the DB level constraint and enforce the relationship in the ORM model and the router instead.
8. Any write to the on disk project folders (project_plan.md, change_summary.md, project_preview.html, requirements.md) goes through the Brain and must pass the path safety gate (ensure_within_root) and the dangerous command guard. Protected branches are never force pushed.
9. The frontend follows docs/FLOW_VISUAL_SPEC.md. Orange is the only brand color. All colors and fonts come from CSS variables, never hardcoded hex in components.
10. Do not commit .env, secrets, build artifacts, node_modules, or the Python virtualenv. Keep .gitignore current.
11. Commit after every update. As soon as a change is complete and verified, stage the explicit paths and commit it with a clear conventional message. Do not leave finished work uncommitted or batch unrelated changes into one commit. Push when the user asks.
12. Destructive endpoints soft delete by default, hard delete is never the default. A delete flags the row (for example a deleted marker in a JSON config blob, or a status or deleted_at column) and keeps it, along with its related rows, so the record stays recoverable. Soft deleted rows are excluded from default lists and their operations return 404 as if gone. A true hard delete is only ever an explicit, separately named action, never the behaviour of the standard delete.

## Navigation (user interface)
- Flow is shown as Project Builder in the interface. The internal pipeline name, the API paths, and the code stay Flow. The rename is presentation only.
- Inbox and Reminders are removed as top level tabs. Capture lives in a global command bar and in the Project Builder capture stage. Reminders fold into Tasks.
- Canonical sidebar order, top to bottom: Dashboard, Insights, Journal, Tasks, Research, Focus, Project Builder, Projects, Settings. Dashboard is the default landing route. A global command bar above the sidebar owns Capture.
- Settings sub tabs, in order: General, Users, Integrations, Knowledge, Skills and Connectors, Models and Agents, System.
- Knowledge is a Settings sub tab, not a top level sidebar item and not a tab named Memory. Inside Knowledge the internal tabs are General, Personal, Development, API connections, Dreaming. The memory candidate review and approval queue lives in Settings, Knowledge, Dreaming, and is also surfaced on the Dashboard as the Dream Digest.

## Model router
The Brain selects a model by semantic key from services/brain/config/models.yaml, never by hardcoding a model id in business logic. Keys at minimum: general, agentic_code, research_synthesis, bulk, journal_reflection, vision. Resolve the concrete model through the router so a key swap is a config change.

## Dev commands (keep this section current as the build grows)
- Brain: cd services/brain, create a venv, pip install, alembic upgrade head, uvicorn app.main:app --reload --port 8847.
- Web: pnpm --filter web dev.
- Desktop: pnpm --filter desktop tauri dev.
- Client regen: pnpm gen:client after the Brain OpenAPI changes.

## Working style
Prompts are pasted one at a time from docs/BUILD_PLAYBOOK.md. Close a prompt's acceptance criteria before advancing. Prefer a stated recommendation over a menu of options. Keep this file updated when a decision or a model name changes.
