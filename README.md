# Nexus ATOM GEOS Agent and Model Plugin

The first ATOM model plugin and the flagship modernization workflow. It exposes `geos.inspect`, `build`, `test`, `sanitize`, `run`, `profile`, `benchmark`, `optimize`, `repair`, `reproduce`, `validate` and `diagnose` through Core capabilities. The shared controller never imports GEOS compilation logic.

The workflow inspects the repository federation, creates detached worktrees, builds/runs/benchmarks/profiles a baseline, applies a checked proposal, then builds/runs/benchmarks the candidate and evaluates software, numerical, science and performance evidence. Regression workflows omit performance stages. Debug workflows reproduce a specified failure and verify a repair against a trusted reference; see the [debugging example](docs/USAGE.md#reproduce-and-repair-a-failure). Failed candidates remain rejected. Source commits, policies, job logs, generated fields, repeated timing samples, proposals and patches become sealed experiment evidence.

```bash
atom run --system geos --demo --state .atom/geos-demo --target speedup=1 \
  'Optimize a synthetic kernel while preserving exact results'
```

This runs a real local engineering lifecycle on a **synthetic Python kernel**, not a GEOS model or GPU. Performance numbers from this example must not be reported as GEOS speedups. [Discover setup and actual model execution](docs/DISCOVER.md) require your allocation, GEOS checkout, baselibs/modules, model inputs, commands and approved science criteria.

The plugin supports prepared file proposals and configured local/NOOA agents with explicit source targets. It imports mepo layouts through the preserved repository registry and rejects dirty baselines, stale source hashes, path escapes and changes outside selected agent targets. Commands run in detached worktrees. Baseline/candidate commands and Slurm resources can differ, while experiment identity and data must remain comparable. Slurm benchmarks require fresh application timing files; queue time is never treated as compute speedup.

This repository is the canonical home of the GEOS Agent. It includes all six NOOA
specialists, source tools, durable sessions, and the `geos-agent` CLI, alongside
the `nexus_atom_geos` plugin. You can use the agent CLI without running ATOM
Controller. [Agent usage](docs/AGENTS.md) explains the roles and tool composition;
[readiness and setup](docs/READINESS.md) gives runnable commands.
The implementation originated in `nasa-nccs-hpda/nexus-geos-agent` under Apache-2.0;
its source, tests, fixtures, history, and release tags are preserved here. See
[migration coverage](docs/MIGRATION.md). The old repository is no longer required.
Install `[nooa]` for live specialist reasoning and the scripted NOOA example.

ECCO, LIS, ISSM and ModelE entry points are included as small **synthetic plugin contract examples** in `nexus_atom_geos.examples`. Run them with `atom run --system ecco --demo ...` (substitute the model name). They exercise the shared controller/evaluator/artifact protocol and do not claim upstream model execution. Separate production model repositories are deliberately deferred as specified in the plan.

## Install

Python 3.12–3.13, Linux or macOS. The six packages are released together; they are not yet published to PyPI. Clone `nexus-atom-controller` and run its `scripts/bootstrap.py --directory ../NexusATOM` to clone the matching release and create a virtual environment. Use `--ref main --dev` for development. Existing checkouts are preserved.

From a workspace containing all six repositories:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ./nexus-atom-core -e ./nexus-atom-controller \
  -e ./nexus-atom-agents -e ./nexus-atom-hpc -e ./nexus-atom-science -e ./nexus-atom-geos
.venv/bin/atom plugins
```

Run package tests with `python -m pytest tests` after installing the `dev` extra and sibling dependencies. The GEOS legacy tests also require the `nooa` extra; GEOS integration tests require the controller. CI tests Python 3.12 and 3.13 and builds wheel/sdist artifacts. See the [architecture and implementation map](https://github.com/NexusATOM/nexus-atom-controller/blob/main/docs/ARCHITECTURE.md).

Apache-2.0. This is an independent implementation for model orchestration, not an official NASA model distribution or endorsement.

## Documentation

- [How to use and orchestrate the agents](docs/AGENTS.md)
- [Optional repository/science specialists and improvement inputs](docs/SPECIALISTS.md)
- [Setup and readiness](docs/READINESS.md)
- [Migration coverage and preserved history](docs/MIGRATION.md)

- [Discover configuration](docs/DISCOVER.md)
- [Usage and configuration](docs/USAGE.md)
- [Python API reference](docs/API.md)
- [Contributing](CONTRIBUTING.md)
- [Execution boundaries](SECURITY.md)
- [Changes](CHANGELOG.md)

Configured `software_checks: [test, sanitize]` add required baseline/candidate check stages and separate acceptance evidence. See [required tests and sanitizers](docs/USAGE.md#required-software-tests-and-sanitizers); the default empty list makes no test/sanitizer coverage claim.

Use `workflow: regression` for baseline/candidate software and scientific comparisons
without performance stages. See [regression usage](docs/USAGE.md#regression-checks-without-an-optimization-objective).
