# First executor dogfood run

The north star moment: nexaOSweb ran a small real build through its own executor, model driven,
recorded end to end, parked at the human gate, nothing merged.

## How it was run

A provider key was connected (Settings, Models and Agents). A small project was seeded with a
requirements.md, then the watched entrypoint drove the loop:

```
cd services/brain
python -m scripts.run_executor <project_id>
```

requirements.md:

```
# Requirements

- Add a short project README describing the goal
- Add a CONTRIBUTING note with one setup step
```

## What happened

The run produced seven steps on the AgentRun and AgentStep spine and stopped at the approval
gate. Nothing was merged.

```
[ 1] plan             planned             Add a short project README describing the goal
[ 2] plan             planned             Add a CONTRIBUTING note with one setup step
[ 3] edit             completed_verified  Edit docs/plan/01-add-a-short-project-readme...md
[ 4] edit             completed_verified  Edit docs/plan/02-add-a-contributing-note...md
[ 5] check            completed_verified  Check requirements-present
[ 6] diff             completed_verified  Worktree diff versus base
[ 7] approval_request waiting_approval    Approve before leaving the worktree
run status: waiting_approval. Parked at the gate, nothing merged.
```

The edit steps were authored by the agentic_code model (claude-opus-4-8) through the router, with
real file writes as tool evidence, so they are completed_verified. The check ran a real command
with a real exit code. The run parked at waiting_approval, and merge_on_approval was never called,
so nothing left the worktree.

## A real bug the dogfood surfaced

The first run fell back to offline synthesis because the agentic_code model call failed:
claude-opus-4-8 deprecates the temperature sampling parameter, which the router was sending. Two
fixes landed:

- config/models.yaml: the agentic_code entry no longer sets temperature.
- the router retries once without a deprecated sampling parameter named in a provider error,
  rather than failing the whole call.

After the fix the rerun used real model authored content (a genuine CONTRIBUTING.md draft), the
same seven step shape, still parked at the gate.

## What this proves and what is next

The gated, evidence backed, human in the loop executor loop works against a real model. The
remaining executor work (P4-RUNTIME-HARDEN timing and cost fields, the Operations surface, the
project Run Timeline view) makes the run watchable in the UI. A first multi agent loop and the
app builder templates come after, only on top of this proven loop.
