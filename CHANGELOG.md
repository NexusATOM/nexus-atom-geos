# Changelog

## 0.2.0 — 2026-09-18

- Add SQLite-backed GEOSSession state: objectives, task dependencies, decisions,
  findings, repository snapshots, artifact hashes and attempt history.
- Add session creation, queuing, execution, retry, recovery, integrity verification,
  scoped memory promotion and an interactive `resume` interface.
- Pass bounded historical findings to specialists without sharing private chat histories.
- Enforce one worker per session, detect changed Git checkouts before execution,
  retain interrupted attempts and require explicit retries at task boundaries.
- Test reopening databases, dependency failure, worker exclusion, artifact tampering,
  historical-context injection into real NOOA and persistent engineering candidates.

## 0.1.0 — 2026-09-18

- Import all mepo components and permit explicit bindings beyond the curated catalog.
- Respect Git ignore rules when gathering source context from real checkouts.
- Fingerprint dirty tracked and newly created source files during benchmark trials.
- Record runtime/model configuration and cap generation output tokens.
- Feed measured baseline timing evidence through PerformanceAgent, architecture
  synthesis and coding proposals without treating whole-command timings as kernel profiles.
- Add reproducible dependency lock, Python 3.12/3.13 CI, package build checks,
  full synthetic engineering demo and site integration templates.
- Document public APIs, scientific limits, execution boundaries and release workflow.
- License original project code under Apache-2.0; upstream libraries remain external dependencies.

## 0.1.0a3 — 2026-09-18

- Add GEOSWorkspace and the integrated `work` engineering lifecycle in detached worktrees.
- Enforce baseline/candidate build and validation gates, fresh numerical artifacts,
  repeated benchmarks, optional speedup thresholds and up to three model repairs.
- Add dry-run-first named command execution with process-group timeouts and output limits.
- Add digest-guarded patch review/application, preflight checks, backups and rollback.
- Compare finite field values with explicit units, shapes, tolerances, binary64
  bitwise checks and optional unweighted conservation checks.
- Produce machine-readable and Markdown engineering reports with source and measurement provenance.
- Test the lifecycle against real temporary Git worktrees and real subprocesses.

## 0.1.0a2 — 2026-09-18

- Compose six real NOOA agents using typed PredictStrategy methods.
- Add bounded investigation, explanation, GPU planning and patch-proposal workflows.
- Validate citations against repository-specific evidence and record delegation events.
- Add CLI, offline synthetic example, and persistent JSON/JSONL run artifacts.
- Test actual NOOA method dispatch with its scripted FakeLLMClient (no API keys).

## 0.1.0a1 — 2026-09-18

- Establish typed GEOS tasks, repository bindings, evidence and result contracts.
- Add a curated GEOS catalog with the real FV3 wrapper/core repositories.
- Import local mepo manifests without cloning or changing pinned component refs.
- Bound source context and record file digests, line ranges and Git state.
- Cover routing, aliases, nested repository isolation, path escapes and budgets.
