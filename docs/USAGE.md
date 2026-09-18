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

`modernization_plan`/`gpu_port_plan`/`optimize_plan` build the full baseline/candidate sequence. `regression_plan` executes and compares baseline/candidate runs without performance stages; select `workflow: regression` in configuration. `debug_plan` reproduces a specified failure, records diagnostics, applies a repair, and compares the repaired output against a trusted reference; select `workflow: debug` (see below).

## Site configuration fields

| Field | Meaning |
|---|---|
| `workflow` | `modernization` (default), `regression`, or `debug` |
| `workspace` | YAML federation bindings; relative to the config file |
| `repository` | Bound repository in which site commands run |
| `backend` | `local` or `slurm` |
| `resources`, `environment` | Shared HPC resource/module/container settings |
| `commands` | Argument vectors for build/run/benchmark/profile |
| `phase_commands`, `phase_resources` | Optional baseline/candidate overrides |
| `dataset` | Repository-relative fresh scientific output file |
| `benchmark_seconds_file` | Repository-relative JSON file containing positive finite `seconds`; required for Slurm |
| `repeats`, `warmups` | Measured trials (3–100) and warmups (0–20) |
| `benchmark_identity` | Required when benchmarking: explicit workload/environment identity for comparable runs |
| `tolerance` | Absolute/relative or bitwise numerical policy |
| `science` | Nonempty suite of explicitly approved diagnostic thresholds |
| `proposal` | Prepared PatchProposal JSON path; relative to config |
| `runtime_argv`, `nooa_model` | Alternative proposal-generation runtime |
| `targets` | Explicit repository/path pairs an agent may modify |

A prepared proposal takes precedence over live generation. Remove it when enabling a runtime. Default prepared workflows execute one candidate; agent-backed workflows can propose further attempts using prior evaluator feedback until a budget/goal stopping condition. Profile information is retained as evidence; advanced automated profiler interpretation remains a runtime/plugin extension.

## Validation and boundaries

Modernization requires evaluators `geos.software`, `geos.numerical`, `geos.science` and `geos.performance`. Software checks configured command success. Numerical/science checks read fresh captured datasets. Performance computes median baseline/candidate timing ratio from repeated samples and requires matching declared identity. Proper hardware/input/measurement control remains part of the site setup.

A wrong candidate is never promoted merely for being fast. Passing configured diagnostics is not a universal GEOS science certificate. Promotion records a best-candidate pointer and retains source/worktrees; it does not merge upstream branches.

## GEOS Agent tooling

`geos-agent` is maintained here alongside the plugin. Start with [how to use the agents](AGENTS.md). Its repository inspection, typed NOOA agents, engineering gates and durable session interface are documented under [legacy usage](legacy/USAGE.md), [legacy sessions](legacy/SESSIONS.md), [legacy API](legacy/API.md) and [legacy architecture](legacy/ARCHITECTURE.md). These are retained interfaces, separate from the new `atom` controller.

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

The modernization plan profiles the candidate after benchmarking it as well as
profiling the baseline. Later proposal attempts receive that candidate profile
through prior task results. Use `phase_commands.candidate.profile` for a distinct
candidate profiler, otherwise the common profile command is used; configurations
with only `phase_commands.baseline.profile` reuse it for the candidate. A failed
profiler fails the experiment rather than certifying an incompletely measured
candidate. Each attempt still starts from the original isolated baseline.

## Required software tests and sanitizers

Configure `software_checks` to require separately recorded stages after each
baseline and candidate build:

```yaml
software_checks: [test, sanitize]
commands:
  # Merge these with the existing build/run/benchmark/profile commands.
  test: [ctest, --test-dir, build, --output-on-failure]
  sanitize: [./ci/run-sanitizers.sh]
```

These are illustrative site commands, not scripts shipped for GEOS. The sanitizer
runner must perform the intended instrumented build/execution and return nonzero
when it detects an error. Configure its compiler flags, tools, suppressions and
input coverage explicitly. A command's name alone does not establish that it
performed meaningful tests or sanitizer analysis.

Both phases require a command for each selected check. Use `phase_commands` to
supply different CPU/GPU check runners. Jobs use the same resource/environment
selection, deadlines, logs and accounting as build/run jobs. Each phase produces
`evidence/<phase>-test.json` and/or `evidence/<phase>-sanitize.json`, plus complete
job logs and bounded excerpts. A failure blocks downstream tasks and reaches the
next proposal as task feedback.

The default plugin goal adds `geos.tests` and `geos.sanitizers` as appropriate.
The `geos.software` evaluator also requires the selected checks, so a custom plan
cannot skip them and rely only on successful build/run evidence. Missing evidence
fails acceptance. Runtime-generated plans must include `geos.test` and/or
`geos.sanitize` in both phases when these checks are required by configuration.

The default empty list preserves existing configurations and explicitly means
that separate tests/sanitizers were not required. Site-policy artifacts record
this selection. Production acceptance should declare the checks appropriate to
the experiment; existing synthetic demos do not claim real sanitizer coverage.

## Timing exports

Each successful benchmark also writes `evidence/baseline-timings.csv` or
`evidence/candidate-timings.csv`. Rows contain phase, measured trial number,
seconds, and measurement scope. Warmups are excluded exactly as in the benchmark
JSON. Both formats retain the same sample values and are sealed as artifacts.
The controller's `_atom_report` files provide acceptance decisions and metrics;
CSV exports alone do not imply that a candidate was accepted.

## Automatic scientific comparison plots

Install `nexus-atom-geos[plots]` and set `plot_fields` to a list of field names in
GEOS configuration, for example `plot_fields: [synthetic_mass]` for the synthetic
demo dataset. The default empty list disables automatic plotting. Missing
Matplotlib is detected when creating a plugin with plots configured.

The `geos.validate` capability compares the selected baseline/candidate fields
and writes `evidence/plots/field-0000.png` (and subsequent numbered files), plus
an `evidence/plots.json` manifest mapping field names to hashed plot artifacts.
Controller includes these files in the sealed experiment snapshot. Plots are
also retained when numerical/scientific checks fail; their existence cannot
make a failed comparison acceptable.

Inputs must have aligned units, shapes, dimension names, and coordinates and
must be one- or two-dimensional. Select/slice higher-dimensional model output
explicitly before providing it. Missing fields or incompatible data fail the
task. Profiles use available coordinates; two-dimensional plots show grid
indices, not geographic projections. The manifest preserves the original field
names while filenames use safe ordinal identifiers.

## Regression checks without an optimization objective

Set `workflow: regression` in the GEOS configuration. The default plugin planner
then executes inspect → baseline build/checks/run → optional prepared patch →
candidate build/checks/run → numerical/scientific validation. Configured
`software_checks` remain mandatory in both phases. Plots and sealed reports work
as in modernization. No benchmark, profiler, or speedup acceptance is implied.

Provide `proposal` to compare a prepared source change against the baseline.
Without a proposal, both phases use unchanged source; this checks repeated-run
behavior (or explicit phase-command configurations), not a new source version.
Commands still need to recreate the relevant build/run conditions. The framework
does not infer a compiler matrix, restart protocol, or clean-build policy.

Only build/run and configured test/sanitizer commands are required for this
workflow. Benchmark identity, profiler commands and Slurm timing output are
required only if benchmarking is actually used. Regression rejects configured
proposal runtimes and speedup targets rather than silently generating edits or
claiming an unmeasured performance result. It runs one recorded comparison;
completed resume returns the recorded state without repeating the candidate.

```bash
atom run --system geos --config regression.yaml --state .atom/regression \
  'Check the prepared change against the reference outputs'
```

`regression.yaml` uses the same workspace, dataset, tolerance and scientific suite
fields as modernization, with `workflow: regression`. The required evaluators
are software, numerical and science, plus separately configured test/sanitizer
gates. The baseline itself must satisfy the configured software checks. Diagnosing
or repairing a failing baseline belongs to the debug workflow below; a failed
baseline must not be accepted as regression success.


## Reproduce and repair a failure

Select `workflow: debug`, supply one prepared `proposal` or repair runtime
(`runtime_argv`/`nooa_model` with explicit `targets`), and configure:

```yaml
debug:
  reference_dataset: reference.json
  reference_sha256: <64-character SHA-256 of the reference file>
  expected_exit_code: 1
  failure_signature: "known failure message"
  signature_stream: stderr
  protected_files:
    - [MAPL, tests/reproducer.py]
commands:
  reproduce: [python, tests/reproducer.py]
  build: [./build.sh]
  run: [./run.sh]
```

Keep the existing workspace, science and tolerance settings. The reference must
have the same fields, units, coordinates and experiment metadata as candidate
output. Its bytes are verified and snapshotted before execution. Reference
selection and scientific tolerances are operator decisions.

The sequence is inspect → reproduce → diagnose → repair → build → configured
software checks → run → reproduce → validate. Baseline reproduction must fail
with the specified exit code and literal signature; candidate reproduction must
succeed using the same command and resources. The baseline failure is retained
as evidence, not treated as a passing program. Diagnostics record observations,
not a proven root cause. Runtime proposals receive those observations plus prior
attempt feedback. A prepared patch gets one attempt. No speedup target applies.

Protected files are fingerprinted, checked around reproduction, and excluded
from patches. Protect your reproducer and test harness; these controls are not a
sandbox for arbitrary operator commands. The additional `geos.repair` gate and
the software gate require reproduction/repair evidence, while numerical and
science gates compare against the trusted reference (not failed baseline output).

Run a complete synthetic example from this repository after installing the
Controller and GEOS package:

```bash
python examples/debug_demo.py /tmp/atom-debug-example
atom run --system geos --config /tmp/atom-debug-example/debug.yaml \
  --state /tmp/atom-debug-example/state 'Repair the synthetic bug'
```

This fixes an intentionally wrong arithmetic result with a prepared patch, uses
no provider, and retains the original source. It demonstrates orchestration,
not real GEOS debugging or scientific validation. Inspect the recorded goal and
experiment with the Controller commands in its usage guide; resuming a completed
goal reuses the saved results.


## Replanning from prior changes

Successful `optimize` and `repair` tasks record `proposal_feedback` in their
outputs. It includes the exact proposal JSON when it fits within 64 KiB, otherwise
an explicitly truncated head/tail excerpt. The full proposal remains at
`evidence/proposal.json` in the originating experiment; the feedback records its
SHA-256 and byte count. Truncated text is context, not a complete JSON document.

The default plugin planner carries the latest attempt's task results to the next
runtime invocation, including this patch context alongside compiler errors,
measurements and evaluations. Controller history and checkpoints preserve the
same feedback across resume. Source and proposal text are untrusted evidence,
not instructions or permission to relax acceptance checks.

With the default `continuation: original`, each trial starts from the original
configured source. Generate a complete
replacement proposal against the current supplied file hashes; do not return an
incremental patch against a prior candidate. A valid candidate below the goal
may inform a new proposal, but `best_valid_candidate` does not automatically
change the source checkout. Opt-in continuation is described below.
Proposals rejected before successful patch application do not produce this
feedback record; task failure details remain available.


## Continue from the best accepted candidate

For runtime-driven modernization, set:

```yaml
continuation: best_valid
```

This requires `workflow: modernization`, a local or NOOA proposal runtime,
and explicit source `targets`. It is not supported for prepared patches,
regression or debug workflows. The default remains `original`.

Controller supplies its selected `parent_experiment` to execution; a model cannot
select a different parent through task parameters. GEOS still builds, runs,
profiles and benchmarks the original configured source first. Before requesting
the next proposal it verifies the parent's sealed cumulative proposal and
original commit records, applies that proposal to the new detached worktrees,
and records a local seed commit. Original checkouts and prior experiments are
unchanged. Git hooks and signing are disabled for this internal seed commit.

The runtime receives the reconstructed source and hashes plus `continuation`
metadata, plus the parent candidate’s recorded profile, benchmark and validation
results. It must propose incremental replacements against those supplied hashes.
The new candidate is compared against the original source in the current
attempt, so reported speedup is total improvement, not a multiplied chain of
ratios. A rejected or dominated candidate does not become the next source base.
The controller's existing multidimensional promotion policy selects the parent.

`evidence/continuation.json` records parent and policy. `proposal.json` records
the incremental change; `cumulative-proposal.json` records the complete bounded
replacement against original source. The latter retains original before-hashes
when the same file changes again. Existing proposal limits apply to the union
of changed files (at most 12); exceeding them fails before applying the next patch.
Inherited edits must stay within configured targets. A changed original commit,
missing/corrupted artifact, stale before-hash or invalid parent fails closed.
Legacy experiments lacking a cumulative proposal cannot seed continuation.

Continuation persists across goal resume. The automated synthetic case accepts
one change, rejects the next, then successfully repairs from the earlier accepted
candidate after a process/store restart. Its timing values are scripted test
inputs and provide no performance evidence for GEOS.


## Optional specialist review tasks

Set inline `specialists`, explicit `objective_tags`, and optional per-profile
`specialist_runtimes` in the GEOS config to review runtime-generated changes
before applying them. See [ATOM specialist configuration](SPECIALISTS.md#use-optional-profiles-inside-atom)
for routing, saved state, scope and accounting limits. Existing configurations
without profiles retain their existing task graph.
