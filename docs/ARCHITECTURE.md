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
| `v0.1.0` | Execution and validation tools, patch lifecycle, CI, documentation, release checks |

The first release supports investigation, explanation, GPU-port planning and
reviewable implementation proposals. Production GEOS runs require a configured
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
