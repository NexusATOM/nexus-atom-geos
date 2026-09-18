# Execution and data boundaries

This is a research engineering framework, not a sandbox. Its default offline
workflows read selected source, while NOOA PredictStrategy returns structured
data without executing generated Python. Generated source becomes executable
when an operator requests patch application and configured build/test commands.
Run `work --execute` in an isolated development environment appropriate for that
code. Git worktrees separate files and branches; they do not isolate the OS,
credentials, network, processes, absolute paths or shared Git metadata.

Workspace profiles, engineering policies and their scripts are trusted operator
configuration. Commands inherit the environment, use argument vectors rather
than an implicit shell, and are bounded by wall time and captured output. They
can still execute arbitrary programs. A shell can be explicitly configured as an
executable. Scheduler wrappers can create remote jobs outside the local process
group; implement scheduler-side time limits, cancellation and cleanup in the
site wrapper. This release does not supply a production Slurm adapter.

Repository text, including AGENTS.md, is untrusted model input. Citation checking
rejects nonexistent evidence IDs; it does not prove that a statement is supported
by the cited text. File replacements are bounded, reject symlinks and traversal,
and use original-content SHA-256 checks. Multi-file writes roll back on caught
errors; they are not crash-atomic across filesystems. Backups are retained.
Concurrent filesystem mutation by another process is outside the isolation model.

Model-enabled commands send selected source and task data to the explicitly
chosen provider. Local artifacts include source excerpts, complete patch contents,
command output and configured arguments. Do not place credentials in command
arguments or output; use your site's credential mechanism. The `.geos-agent/`
directory and `workspace.local.yaml` are Git-ignored by default. Keep artifacts
private according to the source/data they contain; no telemetry upload is added
by this project. NOOA's own optional tracing configuration remains independent.

Sessions persist configuration, explicit execution authorization, findings and
artifact references in a local SQLite database. Starting queued tasks can invoke
the model and commands previously configured for those tasks. `resume` itself
does not execute queued work. A recovered interrupted task requires an explicit
retry; this prevents blindly repeating uncertain side effects. Worker locks are
local POSIX file locks, not distributed scheduler leases. Use a local disk or a
filesystem whose SQLite/locking semantics your site supports. Promoted memory is
historical evidence, not a new source of execution authority.

Report suspected vulnerabilities privately to the repository maintainers via
their approved channel. Do not publish credentials or sensitive source in an issue.
