# Release 0.1.0

## Delivered

- A Python package and `geos-agent` CLI using NVIDIA NOOA 0.0.10.
- Curated GEOS expertise plus complete local mepo component binding.
- Six real NOOA agents, isolated repository context, measured baseline timing
  diagnosis, explicit file proposals and bounded repairs.
- An opt-in `work` pipeline with retained detached worktrees, ordered build/test
  gates, fresh numerical comparisons, baseline/candidate benchmarks, and reports.
- Standalone inspection, patch, execution, numerical and benchmark tools.
- Tests, examples, CI, locked dependencies, API/site documentation and Apache-2.0 license.

## Verification record

Verified locally on macOS arm64 on 2026-09-18:

| Check | Result |
| --- | --- |
| Python 3.13.1 test suite | 45 tests passed |
| Python 3.12.14 test suite using uv.lock | 45 tests passed |
| Coverage | 93% on the Python 3.13 run |
| Ruff lint and formatting | Passed |
| Real NOOA dispatch | Passed with scripted FakeLLMClient; no API keys |
| Synthetic end-to-end demo | Passed with real Git worktrees and subprocesses |
| Wheel and source distribution | Built as 0.1.0 |
| Fresh wheel installation | CLI, offline workflow and NOOA inheritance passed |

Tests cover failing baselines and candidate gates, stale artifacts, numerical
mismatches, a bounded LLM repair, unchanged original checkouts, nested mepo
placement, digest conflicts, patch rollback, command deadlines/output caps,
units/shapes/NaNs, and comparable benchmark environments.

The CI workflow runs the locked suite on Linux with Python 3.12 and 3.13 and
builds/installs a wheel. Its hosted execution is pending a push; local checks are
not described as a completed GitHub Actions run.

## Explicitly unverified or deferred

No live paid provider call, production GEOS build, Discover/Slurm job, GPU kernel
port, or GEOS scientific validation was run during this release. NOOA's real
runtime and typed dispatch were tested using its fake client, not a substitute
agent framework. Production use requires the site's source/configuration/data,
wrappers, approved numerical policy and hardware.

Native NetCDF/restart comparison, a semantic Fortran call graph, an automatic
Slurm client, persistent expert memory, unattended merge/push, and broad recursive
modernization are future extensions. Existing command wrappers and explicit
repository bindings are the integration points; the code does not claim those
capabilities already exist.

## Repository milestones

- `v0.1.0a1`: registry, mepo import, typed source evidence.
- `v0.1.0a2`: NOOA workflows, CLI, offline source example.
- `v0.1.0a3`: isolated engineering lifecycle and deterministic gates.
- `v0.1.0`: locked, documented, tested initial release.

Tags are annotated and local. No branch/tag push, GitHub Release or package-index
publication is performed automatically. Candidate GEOS task changes are also
left uncommitted for review; the framework's development commits are separate
from any future scientific source changes it proposes.
