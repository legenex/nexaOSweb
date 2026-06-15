# Phase 4 runtime and surface audit

Report only, no code changed. Produced by P4-RECON. The question for every surface: does its
status and activity derive from the agent runtime (AgentRun and AgentStep, written through the
four runtime writers) or from legacy state (Project.stage, PMRun, BuildLogEntry). This is the
truth table the rest of Phase 4 builds on.

Source of truth for the runtime: AgentRun and AgentStep are defined in
services/brain/app/models/runtime.py (AgentRun at class line 32, AgentStep at 88). The writers
and the state names live in services/brain/app/runtime.py. The read API is
services/brain/app/routers/runtime.py.

## 1. Per surface truth table

| Surface | Web feature dir | Brain router(s) | Status source | Verdict |
|---------|-----------------|-----------------|---------------|---------|
| Dashboard | features/dashboard | /dashboard/summary, /dashboard/brief | Project.stage and InboxItem.status for visibility, AgentRun counts for run tiles | Mixed |
| Insights | features/insights | /insights | Insight and InsightRun tables, independent | Independent |
| Journal | features/journal | /journal/entries, /journal/topics | JournalEntry, independent | Independent |
| Tasks | features/tasks | /tasks | Task.status (open, in_progress, blocked, done, archived) | Independent, legacy status set |
| Research | features/research | /research/projects, /research/{id}/runs, findings | ResearchRun, ResearchFinding, independent | Independent |
| Focus | features/focus | /focus/operator, /focus/ranked | Blend: Project.stage and PMRun.active and AgentRun.waiting_approval | Mixed |
| Flow Builder (internal Flow) | features/flow | /flow/items, .../process, .../clarify, .../promote, .../readiness | InboxItem.status and Project.stage for the gate, AgentRun of kind readiness for the readiness panel | Mixed |
| Projects | features/projects | /projects, .../approve, .../editor/*, .../build-log | Project.stage for the gate, BuildLogEntry for the editor and build log | Legacy |

Reading of the table. The runtime spine is fully defined and tested, but most user visible
status is still legacy. Insights, Journal, Tasks, and Research are independent islands that do
not touch the runtime and do not need to for their own correctness. The three surfaces that
narrate "what the system is doing" (Dashboard, Focus, Flow gate) are mixed, and Projects is
fully legacy. Those four are where Phase 4 unification pays off, because the executor (4C)
produces AgentRun and AgentStep, and these surfaces should narrate that, not Project.stage.

## 2. Legacy leans and the smallest safe unification

| Lean | Where | Legacy field | Smallest safe fix |
|------|-------|--------------|-------------------|
| Clarify approval gate | routers/flow.py promote path | Project.stage == "approved" | Gate on an approved approval_request step of a clarify or readiness run, fall back to stage for legacy items |
| Promote to build gate | routers/projects.py approve | Project.stage set to build | Once the executor is live, promote by starting an executor run from the readiness run, not by flipping the stage |
| Focus stale project detection | focus.py | Project.stage in (build, live) | Treat a project as active if stage is build or live OR it has an active AgentRun, prefer the run signal |
| Focus awaiting approval | focus.py | Project.stage == "clarify" | Query AgentRun of kind clarify or readiness at waiting_approval, fall back to stage for legacy |
| Focus PMRun active | focus.py | PMRun.status == "active" | PMRun is a stub. After ignition, read AgentRun of kind executor at an active status, keep PMRun only as an audit link |
| Dashboard visibility | dashboard.py | Project.stage in active stages | Show build or live projects OR projects with an active run, keep stage as the legacy fallback |
| Builder hands off to a stub | agents/builder.py promote_project | creates PMRun(status="active") | After ignition, call start_executor_run instead of creating the PMRun stub, the pm_run_id seam on AgentRun already exists |

Do not unify away BuildLogEntry. It is executor rollback infrastructure, not legacy debt. The
edit phase records a BuildLogEntry with before_content, and rollback reads that before_content
to revert. The AI editor in the Projects workspace also proposes and applies through it. The
safe move is additive: keep BuildLogEntry for rollback and the editor, and add a parallel edit
AgentStep that references the BuildLogEntry id so the runtime carries the full audit trail.

## 3. Executor first run preconditions

The executor is services/brain/app/agents/executor.py, about 1025 lines, written entirely on the
AgentRun and AgentStep spine across four phases (plan, edit, check and gate, merge and deploy).

Two facts confirmed by inspection:

- No model backed synthesize is wired. execute_planned_edits takes a synthesize parameter that
  defaults to None (executor.py around line 446). render_edit in project_editor.py uses it when
  present and otherwise falls back to a no op that returns the original content. So today the
  edit phase cannot produce real file content.
- No production trigger. A grep of services/brain/app/routers for start_executor_run and
  execute_planned_edits returns nothing. Only the tests call the executor. Nothing in a router
  or a script starts a run.

Phase functions and their shape:

- start_executor_run(db, *, readiness_run, project_id=None, proposed_by="system") -> AgentRun.
  Sets up the worktree and branch, plans steps, returns the run.
- plan_steps_from_requirements(text) -> list. Turns requirements.md into planned steps.
- execute_planned_edits(db, run, changes, *, synthesize=None, proposed_by="system") -> list of
  AgentStep. This is the seam where a real synthesize must plug in.
- run_checks_and_gate(db, run, *, checks=None, timeout, proposed_by="system") -> dict. Runs
  lint, typecheck, or tests, computes a diff step, and parks an approval_request step.
- merge_on_approval(db, run, ...) and execute_deploy(...). Deploy is a preview only seam that
  raises rather than acting.

Preconditions for a first real run:

1. A provider key is connected. The store first resolution must return a key for the agentic
   code model, otherwise the synthesize call has no model.
2. A satisfied readiness run. start_executor_run refuses unless the readiness gate is satisfied
   for the project.
3. requirements.md exists for the project, written by promote_project at the end of the gate.
4. Autonomy forced to 0 for the first run, so every step parks at the approval gate and nothing
   merges.
5. A real synthesize callable passed into execute_planned_edits. It should, given a file path
   and an edit instruction, call the agentic_code semantic key through the router and return the
   full intended file content. No hardcoded model id, the key resolves through the store.

Where the real synthesize plugs in: project_editor.render_edit already calls synthesize(before,
instruction). P4-EXEC-IGNITE adds the model backed implementation and a scripts/run_executor.py
that wires readiness, start_executor_run, plan_steps_from_requirements, execute_planned_edits
with the real synthesize, and run_checks_and_gate, stopping at the approval gate.

## 4. Agent runtime model, for reference

AgentRun statuses (services/brain/app/runtime.py): planned, executing, waiting_approval,
blocked, failed, completed. AgentStep statuses include planned, waiting_approval, blocked,
executing, completed_verified, completed_unverified, failed, skipped. A step is
completed_verified only when its evidence is tool sourced, which is the agent writes intent, the
system writes truth rule in code.

The four writers in runtime.py: propose_step (creates a step planned or waiting_approval),
record_execution (sets a terminal outcome and derives verified only from tool evidence),
resolve_approval (the only exit from waiting_approval), correct_step (terminal corrections).

Read API in routers/runtime.py: list runs, get a run, list steps after a cursor, list approval
candidates, resolve a step, list failed steps, status counts, and step proof of work.

## 5. Which 4B surfaces already partly exist

Reuse these, do not rebuild:

- Tasks. A working board already exists in features/tasks with a legacy status set (open,
  in_progress, blocked, done, archived). P4-TASKS-HERMES recolumns it to the Hermes set and adds
  the agent working column linked to a live run. The Task model already has a source field and a
  run link seam to build on.
- Flow Builder. The full pipeline exists in features/flow. P4-FLOW-UI is rename and layout only,
  do not touch the pipeline logic. The approve path still flips Project.stage, which is the gate
  the unification table targets later.
- Research. features/research already has run cards with status and finding counts, per finding
  actions, and synthesis. P4-RESEARCH-CORE adds run feedback, run all, the per run three dot
  menu, finding timestamps, and the left rail history. Reuse the existing endpoints.
- Project editor. agents/project_editor.py is complete (propose, render, apply, rollback) and the
  AI editor tab exists in features/projects/workspace. P4-FLOW-EDIT reuses it, does not rebuild.
- Create from research. Insights already has create task and create project actions and Research
  has finding actions. P4-FLOW-EDIT adds the Create Project button on Research detail that wires
  through these.
- Readiness. agents/readiness.py and the readiness panel in the gate card are complete. The
  executor already checks readiness as a precondition. P4-EXEC-IGNITE consumes it.

## Recommended Phase 4 order from here

P4-PERSIST is done. Next: 4B surfaces (P4-FLOW-UI, then the cross lane research and tasks and
flow edit prompts), then 4C ignition (P4-EXEC-IGNITE with a key connected, then the watched
dogfood run). The unification in section 2 is additive and can land alongside the surfaces that
touch each gate, it does not need a separate migration up front.
