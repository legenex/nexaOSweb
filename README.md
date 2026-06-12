# nexaOSweb

A personal AI operating system. A captured idea travels through a seven stage Flow pipeline (Capture, Classify, Route, Process, Clarify, Human Gate, Execute) and becomes a maintained project.

## One frontend, three targets

A single React frontend serves three targets from the same build:

- A browser companion hosted on Plesk.
- A Mac app, wrapped with Tauri v2.
- A Windows app, wrapped with Tauri v2.

A Python FastAPI Brain holds the data, the model router, and the pipeline. The frontend talks to it through a TypeScript client generated from the Brain OpenAPI. The apps never hold provider secrets, those live only in the server side environment read by the Brain.

## Repo layout

- `services/brain` the FastAPI Brain (SQLAlchemy, Alembic, litellm router).
- `apps/web` the React frontend, the holographic Flow panorama.
- `apps/desktop` the Tauri v2 wrapper producing the Mac dmg and Windows msi.
- `packages/api-client` the generated TypeScript client.
- `docs` ARCHITECTURE.md, FLOW_VISUAL_SPEC.md, BUILD_PLAYBOOK.md, DEPLOY_PLESK.md.
- `design` the canonical visual reference prototype.
- `.github/workflows` ci, desktop installers, deploy.

The root is a pnpm workspace covering `apps/*` and `packages/*`. The Brain is a Python project under `services/brain` with its own `pyproject.toml`.

## Dev commands

- Brain: `cd services/brain`, create a venv, install, `alembic upgrade head`, then `uvicorn app.main:app --reload --port 8847`.
- Web: `pnpm --filter web dev`.
- Desktop: `pnpm --filter desktop tauri dev`.
- Client regen: `pnpm gen:client` after the Brain OpenAPI changes.

## Documentation

- `CLAUDE.md` house rules and project memory, authoritative.
- `docs/ARCHITECTURE.md` decisions, system shape, and contracts.
- `docs/FLOW_VISUAL_SPEC.md` the visual design bible for the frontend.
- `docs/BUILD_PLAYBOOK.md` the ordered build prompts from an empty repo to a deployed system.
