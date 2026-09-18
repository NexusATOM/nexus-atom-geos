# Durable sessions, task graphs and memory

`GEOSSession` separates conversation state from engineering state. NOOA specialists
retain private state only while reasoning. The shared session records objectives,
task dependencies, decisions, source revisions, findings, outputs and artifact
hashes. Later tasks receive bounded historical context rather than copied chats.

## Create and queue work

```bash
geos-agent session create --workspace workspace.local.yaml \
  --objective 'Improve FV dynamics while preserving numerical behavior'

geos-agent session add SESSION_ID 'Inspect pressure calculations' \
  --repo fvdycore --model provider/model

# Use the first command's returned task ID as the dependency.
geos-agent session add SESSION_ID 'Implement the requested pressure optimization' \
  --workflow work --depends-on TASK_ID --repo fvdycore \
  --file fvdycore:actual/path/to/source.F90 --policy site-policy.yaml \
  --constraint exact-numerics --model provider/model --execute

geos-agent session run SESSION_ID --max-tasks 1
```

Without `--model`, an ordinary task gathers offline evidence. An engineering task
can use `--proposal prepared.json` instead of a model. The `--execute` flag saves
authorization to run that engineering task; without it, execution produces a plan
only. Session creation snapshots repository paths and configured commands. Task
creation snapshots the policy/proposal. Edits to the original YAML files do not
silently change already queued work. Create a new session to change its bindings
or command profile.

Task dependencies and optional `--parent` IDs must belong to the same session.
Dependencies only reference existing tasks, making the graph acyclic. A parent is
an organizational relationship; use `--depends-on` to enforce execution ordering.
A task becomes ready only after all dependencies complete. Failed/interrupted
tasks block their dependents. `completed` means the requested operation completed;
an offline inspection or dry-run plan is not a successful scientific experiment.
Inspect each node's result status and its report for what actually ran.

## Resume

```bash
geos-agent resume SESSION_ID
geos-agent resume                 # latest saved session
geos-agent                       # same behavior
geos-agent resume SESSION_ID --status-only
```

On a terminal, resume opens a small REPL:

| Input | Behavior |
| --- | --- |
| `/status` | Show durable state and task results |
| `/history` | Show state-transition history |
| `/agents` | Show assigned coordinators/task status and point to specialist traces |
| `/findings` | Show structured findings with source/run provenance |
| `/run` | Run the next ready task using its saved settings |
| `/retry TASK_ID` | Requeue a failed/interrupted task; does not execute it yet |
| `/decision TEXT` | Record an explicit operator decision |
| `/refresh` | Accept changed repository fingerprints after inspection |
| `/exit` | Close the UI without losing state |
| Plain text | Queue an offline investigation |

Use `session add` to configure live models or engineering tasks. In a noninteractive
process, `resume` prints JSON state and returns; it does not read stdin or run work.
No-argument startup with no saved session explains how to create one.

Completed tasks are not replayed. Before new work, Git revisions and worktree
fingerprints are compared with the session snapshot. If source changed, inspect
it and explicitly run `geos-agent session refresh SESSION_ID`. Historical findings
are still marked historical and must be reverified. Plain folders without Git
do not provide this revision guarantee; prefer real checkouts for engineering.

## Recovery semantics

One POSIX file lock prevents concurrent workers for the same session. After a
process dies, the lock is released. `session recover SESSION_ID` (or interactive
resume) marks abandoned running tasks `interrupted`. A new worker also performs
this check. It **does not automatically replay those tasks**.

```bash
geos-agent session recover SESSION_ID
geos-agent session show SESSION_ID
geos-agent session retry SESSION_ID TASK_ID
geos-agent session run SESSION_ID
```

Retry creates a new attempt directory and a fresh workflow. An engineering retry
creates a fresh isolated candidate from the original workspace snapshot. Previous
worktrees, patches and logs remain available for review. It does not transparently
continue halfway through a compiler process, a model call, or a Slurm job. Clean
up or cancel site-side jobs before retrying uncertain execution. Within a running
engineering attempt, the existing bounded repair loop does reuse its candidate.

## Findings, decisions and long-term knowledge

```bash
geos-agent session decide SESSION_ID 'Use the approved C24/C96 exact-value policy'
geos-agent session promote SESSION_ID FINDING_ID --scope MAPL
geos-agent session memory --scope MAPL
```

Findings retain evidence IDs, source repository/commit, originating run and task
attempt. Explicit promotion copies one finding into a named long-term memory scope.
Use canonical repository names (`MAPL`, `GFDL_atmos_cubed_sphere`) for scopes that
should inform automatically selected repository specialists. Arbitrary scopes
can also be queried explicitly. No semantic/vector search or automatic knowledge
certification is implied. Both findings and memory are bounded before inclusion
in a new prompt; private NOOA chat histories are never copied between specialists.

## Storage and integrity

Default layout:

```text
.geos-agent/
  sessions.sqlite3          # authoritative SQLite state (WAL mode)
  sessions/<session-id>/
    state.json              # replaceable inspection snapshot
    worker.lock
    tasks/<task-id>/attempt-1/<run-id>/
      events.jsonl
      result.json or report.json
      contexts.json, reports, patches, retained worktrees ...
```

The database path is configurable with `--db` on any session command. Use one
local store consistently; this is not a distributed task service. Back up SQLite
using its backup facilities or while writers are stopped, together with artifact
directories and the repositories that own retained Git worktree metadata. Copying
only `state.json` is not a full backup.

```bash
geos-agent session list
geos-agent session history SESSION_ID
geos-agent session verify SESSION_ID
```

`verify` compares recorded artifact hashes with current files and reports missing
or changed files. Git checkout drift is a separate check before execution. Files
from an abruptly interrupted attempt may not yet have registered hashes; their
pre-recorded attempt directory is retained in task state for recovery. The store
rejects unsupported database schema versions rather than modifying them silently.
