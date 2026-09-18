# GEOS Agent setup and readiness

`NexusATOM/nexus-atom-geos` is the canonical home for both the GEOS Agent and
ATOM GEOS plugin. The agent includes six NOOA classes, deterministic repository
and execution tools, isolated engineering workflows, and SQLite sessions.
The old GitHub repository is not required. See [agent usage](AGENTS.md).

## Install the current workspace

Use Python 3.12 or 3.13, Git, and Linux or macOS. From a new parent directory:

```bash
git clone https://github.com/NexusATOM/nexus-atom-controller.git
python3 nexus-atom-controller/scripts/bootstrap.py --directory . --ref main --dev
source .venv/bin/activate
cd nexus-atom-geos
geos-agent --version
python examples/legacy/run_agents_demo.py
python examples/legacy/run_engineering_demo.py
```

`--ref main` includes the latest migration and guides; existing checkouts are
preserved by the bootstrap script and must be updated deliberately. `--dev`
installs the GEOS NOOA extra and test dependencies. The package is not on PyPI;
install the sibling distributions from this workspace. Bootstrap creates all six
repositories, while the `geos-agent` CLI itself does not require Controller.
For an existing workspace and agent-only environment:

```bash
python3 -m venv .venv-agent
source .venv-agent/bin/activate
python -m pip install -e ../nexus-atom-core -e ../nexus-atom-agents \
  -e ../nexus-atom-hpc -e ../nexus-atom-science -e '.[nooa]'
geos-agent catalog
```

Run that second block from the GEOS repository root, with the four named sibling
checkouts present. Do not co-install the old `nexus-geos-agent` distribution:
it owns the same import/CLI names. `geos-agent --version` reports the retained
agent interface version (0.2.0); the enclosing ATOM distribution is currently
0.1.0 with later main-branch improvements.

## Try it and inspect the evidence

The agent demo performs five specialist calls through actual NOOA using scripted
responses, without credentials or provider calls. It prints the specialist list
and paths to the saved result and trace. The engineering demo uses real local
Git worktrees and subprocesses to apply a prepared synthetic change, execute
gates, compare numerical output, benchmark, and write a report. Neither is a
GEOS model run or evidence of GPU acceleration.

```bash
geos-agent investigate 'Trace pressure_log' \
  --workspace examples/legacy/demo/workspace.yaml --repo fvdycore --offline
```

For live reasoning, add `--model provider/model` with an actual supported model
and credentials in the provider environment. There is no default paid call.
[Agent usage](AGENTS.md) explains workflows, individual methods, custom
orchestration, tool integration, and durable sessions.

## Reliability checks and limits

The migrated 55 agent tests exercise actual NOOA fake-client dispatch, citation
rejection, guarded patches, isolated worktrees, failing gates, stale outputs,
command deadlines, numerical errors, sessions, recovery, and artifact integrity.
The same suite is retained under `tests/legacy`. After migration, all 70 GEOS
agent/plugin tests passed locally, with 91.89% agent coverage (including the
module entry point in the denominator). Both examples and the clean-wheel
session/NOOA checks also passed. CI enforces at least 80% `geos_agents` coverage and runs the
broader plugin tests on Linux/Python 3.12 and 3.13. It builds the required wheels
and checks agent sessions and scripted NOOA calls from a fresh installation
without Controller or source-tree imports.

Sessions retain completed work across process exit. Interrupted tasks keep their
evidence and require explicit recovery/retry at task boundaries; they do not
resume arbitrary compiler/provider processes in place. Agent session databases
and Controller experiment stores are distinct interfaces. See
[sessions](legacy/SESSIONS.md) and [execution boundaries](../SECURITY.md).

Production readiness still requires the actual GEOS federation, compiler and
baselibs, Discover allocation/job configuration, representative inputs, and
approved numerical/scientific/performance criteria. Use [Discover](DISCOVER.md)
for the ATOM scheduler or [agent site integration](legacy/SITE-INTEGRATION.md)
for named job wrappers. Local tests do not establish live-provider quality,
production scheduler recovery, scientific validity, or a real GEOS speedup.
