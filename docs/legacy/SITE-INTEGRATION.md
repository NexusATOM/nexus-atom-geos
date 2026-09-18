# GEOS site integration

> These supported GEOS Agent interfaces now live in `nexus-atom-geos`. Follow
> [installation](../READINESS.md), activate that environment, and run commands
> from the repository root. The `legacy` directory records their origin; it
> does not require installing the old standalone distribution.

The library supplies the engineering process. Your site supplies the compiler,
MPI/CUDA stack, ESMF/Baselibs, scheduler allocation, input datasets, restart/oracle
outputs, experiment scripts and scientifically approved tolerances. Do not infer
these from an example. [Workspace](../../examples/legacy/site/workspace.yaml) and
[policy](../../examples/legacy/site/policy.yaml) are templates, not runnable Discover recipes.

## Prepare a reproducible workspace

1. Start from an initialized, clean GEOSgcm fixture and its populated mepo
   components. Record release refs and local commits. Import with `geos-agent init`.
2. Keep every source repository needed by the build in the profile. Import includes
   all components; unknown names can be explicitly bound and selected with `--repo`.
   The curated catalog only adds domain hints and aliases.
3. Add tracked site wrappers to the fixture or a bound site repository. They must
   resolve source paths from their current working directory, because candidate
   checkouts live elsewhere. Avoid absolute paths pointing back to original source.
4. Configure a build wrapper that loads modules and performs **configuration plus
   compilation** in a new worktree. The worktree has no existing build directory.
   Explicitly provision required submodules/external data and generated configuration;
   Git-ignored files and initialized Git submodules are not copied automatically.
5. Put generated logs, build products and numerical exports in Git-ignored directories.
   Baseline commands must leave the source checkouts clean. Benchmark trials must
   not alter source contents; working-tree fingerprints detect tracked and new-file changes.

The catalog models GEOS roles, not the complete scientific dependency graph.
Nested components are isolated at the same relative paths. Extra dependencies
required by a site but absent from the imported manifest must be bound manually
or provisioned by the build environment. Remote URLs are metadata; the framework
does not fetch, update, move tags or clone components automatically.

## Define the validation ladder

`EngineeringPolicy.gates` is ordered and fail-fast. It must start with a `build`
gate and include at least one `validation` gate. Each gate references a named
workspace command; its purpose must be `build` or `test` respectively. Add the
ladder appropriate to your task, such as unit/oracle tests, sanitizers, C24, C96,
C180, C384 and C576. The planning workflow lists possible resolutions, but the
engineering workflow runs only the commands explicitly configured in policy.

Each process must remain synchronous until its work finishes and return nonzero
on failure. A wrapper that only submits `sbatch` and exits zero **does not validate
the job**. On a scheduler, either run the framework within an allocation or use a
site wrapper that submits, waits, checks final scheduler status, validates outputs,
and cancels jobs on failure. Local process-group termination cannot cancel a
remote Slurm allocation. Scheduler integration is currently an extension point,
not a claimed built-in Slurm client.

## Export numerical evidence

Validation wrappers export flattened JSON fields with explicit shape and units:

```json
{
  "fields": {
    "mass": {"units": "kg", "shape": [2], "values": [1.0, 2.0]},
    "temperature": {"units": "K", "shape": [2], "values": [280.0, 281.0]}
  },
  "metadata": {
    "resolution": "C24",
    "time_step": "37",
    "mpi_layout": "6x1",
    "valid_time": "example"
  }
}
```

This first release does not read native NetCDF/HDF5/GEOS restart formats. Use a
site exporter to choose variables, compare time coordinates, normalize units,
mask invalid cells intentionally, and preserve flattening order. Export extensive
quantities or pre-weighted values if requesting unweighted sum conservation checks.
The checker rejects NaN/Inf, empty fields, differing field sets, units or shapes.
It also rejects differing resolution, time step, MPI layout or valid time metadata.
Other metadata is retained as provenance. Missing metadata on both sides is not
evidence of comparability; require it in your exporter for production experiments.

Tolerance mode requires every element to satisfy
`abs(candidate-reference) <= atol + rtol * abs(reference)`. Optional conservation
checks compare sums using the same tolerance formula. Bitwise mode compares
binary64 values reconstructed from JSON, including the sign of zero. It is not
proof of byte-for-byte equality of original NetCDF storage or single-precision
buffers. For exact restart-byte or single-precision checks, configure a separate
site validation command against the native artifacts.

The runner deletes only configured Git-ignored numerical output files before
each phase. Every successful gate sequence must recreate them, preventing stale
baseline artifacts from passing as candidate output. Both datasets and digests
are retained. Missing/malformed output fails the run; it never means “no difference.”

## Define comparable measurements

Benchmark commands have `purpose: benchmark`. Each policy gate specifies hardware,
compiler/options, resolution, MPI layout, thread count and dataset identity.
Warmups are excluded from summaries. The runner records each trial and reports
median/min/max/sample standard deviation of whole-command wall time. It does not
assume that asynchronous GPU work has completed: synchronize in your benchmark
wrapper. Scheduler queue time must not contaminate kernel performance claims.

Environment descriptions are operator-supplied, not discovered guarantees. Keep
them equal for before/after comparisons. A speedup is a descriptive ratio of
measured medians; noisy measurements require review and more careful experiment
design. There is no automatic statistical-significance claim.

## Review, commit and clean up

Read `report.md`, `report.json`, command output, numerical artifacts and each
`proposal.diff`/`backups.json`. Inspect the retained worktrees. The framework leaves
source modifications uncommitted so you can review, create branches, commit and
merge according to your repository policy. It does not auto-merge a science change.

To retain a candidate, create a named branch inside its detached worktree and
commit reviewed changes. To discard one, use `git worktree remove <candidate>`
from the corresponding original repository; Git will refuse dirty worktrees until
you deliberately retain or discard the modifications. Remove deepest nested
worktrees first. Do not delete directories by hand without updating Git's worktree
metadata. Runs record every created path for recovery after partial setup failures.
