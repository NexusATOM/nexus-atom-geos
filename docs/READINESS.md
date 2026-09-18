# Standalone GEOS Agent readiness

This repository provides GEOS engineering tools, six typed NOOA specialists,
isolated candidate worktrees, configured execution/validation gates, and durable
SQLite sessions. It works without the NexusATOM Controller. It is ready for
local development and synthetic demonstrations; production GEOS/Discover and
live-provider acceptance remain to be established.

## Start here

Use Python 3.12 or 3.13, Git, and Linux or macOS:

```bash
git clone https://github.com/nasa-nccs-hpda/nexus-geos-agent.git
cd nexus-geos-agent
uv sync --locked --extra dev
uv run geos-agent --version
uv run geos-agent gpu-port 'Inspect pressure_log' \
  --workspace examples/demo/workspace.yaml --offline
uv run python examples/run_engineering_demo.py
```

The offline command inventories source and proposes a validation plan. The
engineering example applies a prepared change in an isolated Git worktree,
executes build/test processes, compares numerical output, benchmarks, and writes
a report. It runs synthetic Python code, not GEOS or a GPU kernel.
`python -m pip install -e '.[dev]'` also works; the uv lock gives a reproducible
development environment.

## NOOA, execution, and state

`RepositoryAgent`, `ArchitectureAgent`, `CUDAAgent`, `ValidationAgent`,
`PerformanceAgent`, and `GEOSAgent` provide typed specialist reasoning. Live
reasoning requires an explicitly selected model and provider credentials.
CI exercises actual NOOA dispatch with its fake client; this does not establish
live model answer quality. Pydantic validates the data contracts. Deterministic
tools collect source and execute commands; configured gates determine acceptance.
An agent's proposed validation plan is not a passed test.

[Sessions](SESSIONS.md) persist objectives, dependencies, decisions, findings,
attempts, repository snapshots, and artifacts in SQLite. Completed work survives
process exit. `geos-agent resume SESSION_ID --status-only` reads saved state;
`session verify` checks artifact integrity. Interrupted tasks retain evidence
and require explicit recovery/retry at task boundaries. This does not resume
an arbitrary compiler process or provider call in place.

## Relationship to NexusATOM

| Component | Responsibility |
|---|---|
| This repository, `nexus-geos-agent` | Standalone GEOS tools, NOOA specialists, engineering workflow, and sessions |
| [nexus-atom-geos](https://github.com/NexusATOM/nexus-atom-geos) | GEOS capabilities and evaluators for ATOM, plus a retained copy of the standalone tools |
| [nexus-atom-controller](https://github.com/NexusATOM/nexus-atom-controller) | Model-independent goal planning, execution, budgets, experiment sealing, and acceptance |

Use separate environments for this package and `nexus-atom-geos`. Both currently
install `geos_agents` and `geos-agent`; co-installation can overwrite files.
Their session/experiment databases are different interfaces, with no automatic
state migration. ATOM's Slurm adapters and automatic plots do not imply those
features exist in this standalone repository.

Another orchestration system could call these GEOS tools without adopting the
ATOM Controller. No bridge has been implemented or tested. A GEOS/NOOA paper is
a possible scope, but empirical claims require real GEOS tasks and comparisons.

## Verification and production prerequisites

The current local audit passed 55 tests with 91.98% coverage on Python 3.13,
including NOOA fake-client dispatch and session persistence. Lint/format,
locked dependency resolution, isolated wheel/sdist builds, and the synthetic
engineering demo passed. CI runs on Linux/Python 3.12 and 3.13 and checks
installed-wheel session creation, execution, resume, and artifact integrity in
separate processes. See [release evidence](RELEASE.md) for historical results.

Production execution needs the GEOS federation, compiler/baselibs, Discover
allocation and job wrappers, representative inputs, and agreed numerical,
scientific, and performance criteria. See [site integration](SITE-INTEGRATION.md),
[architecture](ARCHITECTURE.md), and [usage](USAGE.md). No real GEOS speedup,
production Discover run, or live-provider quality result is claimed. The package
is available from source; no PyPI publication is implied.
