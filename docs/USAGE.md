# Using the GEOS plugin

Start with the [small model-independent example](https://github.com/NexusATOM/nexus-atom-controller/blob/main/docs/QUICKSTART.md) to understand the process. The GEOS plugin is the next step when you have a real site configuration.

## Commands and capabilities

`atom plugins` discovers GEOS and the bundled Phase II examples. `atom run --system geos --demo --state .atom/geos` exercises the GEOS worktree pipeline on synthetic code. `atom run --system geos --config geos.local.yaml --target speedup=3 OBJECTIVE` executes configured site work. It is an actual execution command, not a dry run.

| Capability | Responsibility |
|---|---|
| `geos.inspect` | Import the bound federation, require clean source, create detached worktrees and record source/policy |
| `geos.build` | Run the configured build/test command in the selected phase's isolated checkout |
| `geos.run` | Remove stale output, run the model wrapper and capture fresh scientific fields |
| `geos.profile` | Run the configured profiler and preserve logs/output |
| `geos.benchmark` | Warm up and collect repeated comparable timings; Slurm requires fresh application timing JSON |
| `geos.optimize` | Load or generate a proposal, validate source hashes/targets and apply it in isolation |
| `geos.validate` | Compare baseline/candidate numerics and configured scientific diagnostics |
| `geos.diagnose` | Persist configured numerical/scientific diagnostic results |

`modernization_plan`/`gpu_port_plan`/`optimize_plan` build the full baseline/candidate sequence. `regression_plan` and `debug_plan` currently build/run the baseline; they are building blocks requiring appropriate goal evaluators, not full autonomous debugging systems.

## Site configuration fields

| Field | Meaning |
|---|---|
| `workspace` | YAML federation bindings; relative to the config file |
| `repository` | Bound repository in which site commands run |
| `backend` | `local` or `slurm` |
| `resources`, `environment` | Shared HPC resource/module/container settings |
| `commands` | Argument vectors for build/run/benchmark/profile |
| `phase_commands`, `phase_resources` | Optional baseline/candidate overrides |
| `dataset` | Repository-relative fresh scientific output file |
| `benchmark_seconds_file` | Repository-relative JSON file containing positive finite `seconds`; required for Slurm |
| `repeats`, `warmups` | Measured trials (3–100) and warmups (0–20) |
| `benchmark_identity` | Explicit workload/environment identity for comparable runs |
| `tolerance` | Absolute/relative or bitwise numerical policy |
| `science` | Nonempty suite of explicitly approved diagnostic thresholds |
| `proposal` | Prepared PatchProposal JSON path; relative to config |
| `runtime_argv`, `nooa_model` | Alternative proposal-generation runtime |
| `targets` | Explicit repository/path pairs an agent may modify |

A prepared proposal takes precedence over live generation. Remove it when enabling a runtime. Default prepared workflows execute one candidate; agent-backed workflows can propose further attempts using prior evaluator feedback until a budget/goal stopping condition. Profile information is retained as evidence; advanced automated profiler interpretation remains a runtime/plugin extension.

## Validation and boundaries

Required evaluators are `geos.software`, `geos.numerical`, `geos.science` and `geos.performance`. Software checks configured command success. Numerical/science checks read fresh captured datasets. Performance computes median baseline/candidate timing ratio from repeated samples and requires matching declared identity. Proper hardware/input/measurement control remains part of the site setup.

A wrong candidate is never promoted merely for being fast. Passing configured diagnostics is not a universal GEOS science certificate. Promotion records a best-candidate pointer and retains source/worktrees; it does not merge upstream branches.

## Legacy GEOS tooling

`geos-agent` remains available. Its repository inspection, typed NOOA agents, engineering gates and durable session interface are documented under [legacy usage](legacy/USAGE.md), [legacy sessions](legacy/SESSIONS.md), [legacy API](legacy/API.md) and [legacy architecture](legacy/ARCHITECTURE.md). These are retained interfaces, separate from the new `atom` controller.

See [API](API.md), [Discover](DISCOVER.md), [example site files](../examples/discover), and [tests](../tests/test_plugin.py).

## Profiling and failure feedback for proposals

Local/NOOA optimization requests include `baseline_profile` alongside baseline
benchmark samples and selected source files. Build, run and profile command
results record bounded stdout/stderr excerpts: the first and last 4 KiB per
stream, with availability, total byte count and a truncation flag. Complete job
logs remain in the experiment artifacts. Configure the profile command to print
useful hotspots or a concise summary to stdout (for example, sort a cProfile
report by cumulative time). A profiler that only writes a separate binary report
must also export a text summary for this proposal context.

On another attempt, the GEOS planner supplies the previous terminal task results
as `previous_task_results`, in addition to evaluator decisions. This preserves
compiler/runtime error excerpts even when a failed task prevents the downstream
validation graph from running. A runtime can use those errors to propose a repair
from a fresh isolated baseline. It is still responsible for interpreting the
profile and choosing a hypothesis; ATOM does not implement a universal profiler
parser or guarantee that the agent can fix a failure.

A regression test uses an actual local JSON proposal process and synthetic GEOS
workflow. The process checks that profiling evidence is present, proposes an
invalid Python candidate, receives its compiler error on the next attempt, and
proposes a valid repair that passes the registered checks. This tests evidence
flow and revision, not live LLM reasoning or actual GEOS optimization.
