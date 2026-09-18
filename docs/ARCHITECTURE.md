# Architecture and delivery plan

Nexus GEOS Agent implements the design in [PRELIM-PLANNING.md](PRELIM-PLANNING.md)
as an evidence-driven Python library and CLI. NVIDIA's package is named **NOOA**
(`nooa`), not NOAA. Python 3.12–3.13 matches its supported runtime.

## Decisions

1. **Real NOOA agents.** GEOSAgent coordinates ArchitectureAgent, RepositoryAgent,
   CUDAAgent, ValidationAgent, and PerformanceAgent. Selected typed methods use
   `PredictStrategy`; deterministic Python handles discovery, context, commands,
   patch application, and numerical comparisons. No LLM-generated Python is
   executed by this release.
2. **Repository federation.** A curated catalog describes GEOS responsibilities.
   A workspace registry binds only explicitly configured local checkouts. The
   GEOS fixture's `components.yaml` supplies actual mepo component paths and refs.
   Checkout containment is distinct from scientific/runtime dependency edges.
3. **Lazy evidence.** Only selected repositories are inspected. Source excerpts
   have file, line, content digest, and Git revision provenance and fixed budgets.
   Repository text is input data, never an authority to change execution policy.
4. **Bounded delegation.** The orchestrator selects a small set of repository
   specialists, then engineering specialists as required by the workflow.
   Explicit repository selections override heuristic routing.
5. **Deterministic execution.** Commands come from a user-authored workspace
   profile, run as argument vectors with time/output limits, and default to dry
   runs. Patch proposals are artifacts; applying one is a separate operation
   requiring unchanged input digests and an explicit apply flag.
6. **Scientific honesty.** Numerical checks do not imply scientific validity.
   Conservation/tendency checks and benchmark measurements have explicit inputs,
   tolerances, and provenance. Missing experiments remain unverified.
7. **Auditability.** Local JSONL events and a JSON result are produced independently
   of NOOA's optional trace viewer. Failures and skipped execution are recorded.

## Initial milestones

| Tag | Deliverable |
| --- | --- |
| `v0.1.0a1` | Typed core, GEOS catalog, mepo import, bounded repository context |
| `v0.1.0a2` | NOOA delegation, task workflows, CLI, reproducible offline example |
| `v0.1.0a3` | Isolated end-to-end work, command/patch lifecycle, numerical and benchmark gates |
| `v0.1.0` | Reproducible installation, runnable demos, CI, documentation, release checks |
| `v0.2.0` | Durable sessions, task graph, shared findings, resume and scoped memory |

The first release supports investigation, explanation, GPU-port planning,
reviewable implementation proposals, and an opt-in end-to-end engineering workflow
through `GEOSWorkspace`. The latter runs in detached Git worktrees, preserves mepo
placement, establishes a baseline, applies changes, runs configured gates, compares
fresh numerical artifacts, measures candidate performance, and writes a report.
Configured failed gates cannot be overridden by a model. Bounded repairs are
limited to the original proposal's files and use fresh content digests.
Production GEOS runs require a configured
HPC environment, data, compiler/MPI stack, and site-specific commands. Automatic
Slurm submission, a complete Fortran call graph, full Earth-system scientific
certification, and unattended multi-repository merges are future extensions.

## Sources inspected

Inspected 2026-09-18. Upstream development source inspected at
`NVIDIA-NeMo/labs-OO-Agents@d4d46f78ae0eeaed7d18a466196601e8d16bc101`;
the install/test contract is the published `nooa==0.0.10` distribution.

- [NOOA](https://github.com/NVIDIA-NeMo/labs-OO-Agents): Agent, PredictStrategy,
  typed generation, per-instance LLM injection, and FakeLLMClient.
- [GEOSgcm](https://github.com/GEOS-ESM/GEOSgcm) and its
  [components.yaml](https://github.com/GEOS-ESM/GEOSgcm/blob/main/components.yaml):
  fixture and mepo layout; import the local file instead of assuming latest tags.
- [FVdycoreCubed_GridComp](https://github.com/GEOS-ESM/FVdycoreCubed_GridComp):
  MAPL/ESMF wrapper around the cubed-sphere dynamical core.
- [GFDL_atmos_cubed_sphere](https://github.com/GEOS-ESM/GFDL_atmos_cubed_sphere):
  dynamical core. The planning document's `GEOSfvdycore` is a compatibility alias
  for this repository, not a claim that such a current upstream repository exists.
- [MAPL](https://github.com/GEOS-ESM/MAPL): ESMF component support, fields, I/O,
  profiling, and testing facilities.
- [ESMA_cmake](https://github.com/GEOS-ESM/ESMA_cmake): shared GEOS CMake macros.

Catalog relationships are curated architecture hints, not a compiler-derived
dependency graph. Paths, tags, branches, and routines must be verified locally.

## Durable session state

`GEOSSession` coordinates a SQLite-backed blackboard through `SessionStore`.
Typed `SessionRequest` and `TaskNode` objects form a dependency graph; references
can only target existing nodes in the same session, so the public API cannot
introduce cycles. Each task has a persisted attempt directory before execution
begins. SQLite is authoritative; `state.json` is an atomically replaced inspection
snapshot. Large evidence stays in files with recorded hashes. Source changes stay
in Git worktrees. Agent-private conversations are not session state.

One OS file lock serializes workers per session. Completed tasks are not replayed.
An abandoned worker becomes `interrupted`; an operator must explicitly retry,
starting a fresh run while preserving earlier artifacts. This is task-boundary
resumption, not transparent continuation of an arbitrary shell process or Slurm
job. Domain validation remains the responsibility of deterministic gates.

Historical findings and explicitly promoted repository-scoped memory can inform
later agents, but must be reverified against current source. Completed historical
checks are never substituted for the new work pipeline's validation ladder.
