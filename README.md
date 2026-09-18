# Nexus GEOS Agent

A GEOS engineering framework built on NVIDIA's
[NOOA](https://github.com/NVIDIA-NeMo/labs-OO-Agents) (`nooa==0.0.10`). It combines
typed specialist agents with deterministic repository tools and validation gates:

**Investigate → propose → modify in worktrees → build → validate → benchmark → report.**

The implementation follows [the planning conversation](docs/PRELIM-PLANNING.md)
and the real GEOS federation: `GEOSgcm`, `GEOSgcm_GridComp`,
`FVdycoreCubed_GridComp`, `GFDL_atmos_cubed_sphere`, `MAPL`, and shared build and
science components. `GEOSfvdycore` remains an alias for the actual dynamical-core
repository. The catalog guides routing; local source evidence supports findings.

## Relationship to NexusATOM

This is the standalone GEOS agent: its NOOA specialists, engineering tools, and
SQLite sessions can run without the NexusATOM Controller or other ATOM packages.
The separate [NexusATOM GEOS plugin](https://github.com/NexusATOM/nexus-atom-geos)
connects GEOS capabilities to the broader goal/experiment controller and shared
HPC/science interfaces. See [the architecture and readiness guide](docs/READINESS.md)
for these boundaries, the runnable example, and production prerequisites.

Use separate virtual environments for this package and `nexus-atom-geos`:
both currently provide the `geos_agents` import and `geos-agent` executable.
Installing both in one environment can overwrite the same files.

See [how to use and orchestrate the agents](docs/AGENTS.md) for all six roles,
CLI/Python examples, tool integration, and saved sessions.

## Quick start

Requires Python 3.12 or 3.13, Git, and Linux or macOS for command execution.

```bash
uv sync --locked --extra dev

# No API key: inspect source and produce a GPU-port validation plan.
uv run geos-agent gpu-port 'Port pressure_log to CUDA' \
  --workspace examples/demo/workspace.yaml --offline

# No API key: execute the complete lifecycle on a temporary synthetic Git repo.
uv run python examples/run_engineering_demo.py
```

The second demo creates worktrees, applies a prepared change, runs real Python
build/test processes, compares fresh numerical output, measures repeated timings,
and writes a report. Both demos are **synthetic, not GEOS science or performance
results**. A conventional `python -m pip install -e '.[dev]'` installation also works.

## Use your GEOS fixture

```bash
uv run geos-agent init --mepo /work/GEOSgcm --output workspace.local.yaml
uv run geos-agent inspect fvdycore --query 'epv' --workspace workspace.local.yaml

# Explicit provider/model and its credential environment enable live NOOA reasoning.
uv run geos-agent investigate 'Trace EPV through the dynamics wrapper' \
  --workspace workspace.local.yaml --repo fvdycore --repo FVdycoreCubed_GridComp \
  --model provider/model

# After configuring your site's commands, outputs, data and numerical policy:
uv run geos-agent work 'Implement the requested GPU optimization' \
  --workspace workspace.local.yaml --policy site-policy.yaml \
  --repo fvdycore --file fvdycore:actual/path/to/source.F90 \
  --constraint exact-numerics --model provider/model --execute
```

`work` without `--execute` reviews the configured plan. With execution enabled it
requires clean input checkouts, preserves nested mepo layout in detached worktrees,
and retains the candidate for review. A configured gate failure cannot be turned
into success by an agent. The framework does not merge candidate branches or
certify scientific validity. Production GEOS execution needs a configured site
environment; it has not been demonstrated by the synthetic tests.

## Durable sessions

```bash
uv run geos-agent session create --workspace examples/demo/workspace.yaml \
  --objective 'Investigate GEOS dynamics and preserve scientific behavior'
# Substitute the returned ID below.
uv run geos-agent session add SESSION_ID 'Inspect pressure_log' --repo fvdycore
uv run geos-agent session run SESSION_ID
uv run geos-agent resume SESSION_ID
```

SQLite stores task dependencies, decisions, findings and artifact references.
Resuming preserves completed work; interrupted tasks require an explicit retry
and retain their previous artifacts. `resume` opens a small terminal interface
with `/status`, `/history`, `/agents`, `/findings`, `/run` and `/decision`.
No-argument `geos-agent` resumes the latest saved session. See [sessions](docs/SESSIONS.md)
for model-driven tasks, shared findings, memory and recovery semantics.

## Capabilities

| Area | Implemented |
| --- | --- |
| Agents | GEOSAgent, ArchitectureAgent, RepositoryAgent, CUDAAgent, ValidationAgent, PerformanceAgent using real NOOA dispatch |
| Repository context | Full mepo import, explicit local bindings, bounded lexical search, excerpts with line/hash/Git provenance |
| Engineering | Named commands, isolated worktrees, baseline/candidate gates, explicit file proposals, up to three model repairs |
| Validation | Finite JSON fields, units/shapes, explicit tolerances, binary64 bitwise comparison, optional unweighted sum checks |
| Performance | Warmups, repeated wall-time trials, environment matching and optional minimum speedup |
| Audit | Persistent JSONL events, source evidence, patch diffs/backups, JSON and Markdown reports |
| Sessions | SQLite task graph, resume/retry, artifact verification, decisions and scoped expert memory |
| Lifecycle | Unit/integration tests, locked dependencies, wheel/sdist packaging, CI and annotated milestone tags |

Read [usage](docs/USAGE.md), [site integration](docs/SITE-INTEGRATION.md),
[architecture](docs/ARCHITECTURE.md), [API examples](docs/API.md),
[execution boundaries](SECURITY.md), [contributing](CONTRIBUTING.md),
[release verification](docs/RELEASE.md), and [changelog](CHANGELOG.md).

Apache-2.0. NOOA and GEOS remain their respective upstream projects; this repository
does not vendor or claim ownership of their source.
