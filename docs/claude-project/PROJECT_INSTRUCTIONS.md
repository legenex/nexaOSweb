# NexaOS project instructions

Paste the body below into the Claude.ai project "Set project instructions" box. It is written
to work alongside the repo CLAUDE.md, which stays the authoritative source of truth.

---

You are helping build nexaOSweb, a web first personal AI operating system. The real codebase is
a React, Vite, TypeScript, Tailwind frontend (apps/web), a Python FastAPI Brain (services/brain)
with a litellm model router, a generated TypeScript client (packages/api-client), and a Tauri v2
desktop wrapper (apps/desktop). One web build serves three targets: a Plesk hosted browser
companion, a Mac app, and a Windows app. This supersedes any earlier native SwiftUI framing.

Before doing anything, read CLAUDE.md and the docs (ARCHITECTURE.md, FLOW_VISUAL_SPEC.md,
BUILD_PLAYBOOK.md). CLAUDE.md is the source of truth and overrides these instructions if they
ever conflict. Inspect HEAD first on every prompt.

Combine prompts whenever it is safe, and say so up front. When I paste prompts:
- Always do your best to combine prompts and run them together rather than strictly one at a time.
- On the line directly above each prompt's ID and name, annotate which other prompt IDs it can run
  together with, for example "Runs with: P20, P-UI1" or "Run alone". Put this annotation next to or
  above the prompt name, before the prompt body.
- Group prompts that are independent: no shared files, no migration ordering conflict, no model or
  config ordering conflict. Web only prompts usually combine well.
- Keep serial: anything with a database migration, a models.yaml or model key change, or where one
  prompt persists what the next one reads. State plainly which prompts must stay serial and why.
- Give one combined plan and a recommended batch order before starting, not a menu.

How to work:
- Cross lane is fine when a prompt assumes backend or data that does not exist yet. Surface the gap
  and propose the smallest Brain plus web path rather than shipping a half wired surface.
- Run pnpm gen:client after any Brain OpenAPI change, before the web that consumes it.
- One commit per logical concern, staged by explicit path, conventional commit messages
  (feat(brain): ..., feat(web): ..., docs: ...). Never git add -A. Commit after every update.
- No em dashes anywhere. Orange is the only brand color, all colors from CSS variables.
- Destructive endpoints soft delete by default and stay recoverable; hard delete is never default.
- Provider secrets live only in the server side .env. The apps never hold keys.
- Verify before claiming done: typecheck, lint, build for web; tests and a live check for the Brain.
  If a run fails live, restart the Brain (Settings, System) and retry before treating it as a bug.

Surfaces, sidebar order top to bottom: Dashboard, Insights, Journal, Tasks, Research, Focus,
Project Builder, Projects, Settings. Project Builder is the user facing name for the internal Flow
pipeline. Knowledge is a Settings sub tab, not a sidebar item.
