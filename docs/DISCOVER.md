# Running on Discover

The controller runs where it can read your checked-out federation and shared experiment storage. Heavy build, model, profile and benchmark commands are submitted through Slurm. Follow your site's policy for controller processes on login nodes; an approved interactive/batch allocation can host the controller when required.

## Bootstrap

Use Python 3.12 or 3.13, Git and your normal Discover authentication. Clone `nexus-atom-controller`, then run its `scripts/bootstrap.py --directory /your/work/NexusATOM`. The script installs the six matching `v0.1.0` repositories in a virtual environment. For unreleased development use `--ref main`. No model source, baselibs or input data is downloaded automatically.

```bash
source /your/work/NexusATOM/.venv/bin/activate
geos-agent init --mepo /your/GEOSgcm --output workspace.local.yaml
cp /your/work/NexusATOM/nexus-atom-geos/examples/discover/geos.yaml geos.local.yaml
```

Fill in the workspace path, allocation, partitions, GPU type, modules, commands, dataset provenance and approved validation thresholds. `REPLACE_*` entries are deliberate placeholders, not Discover defaults. Keep local profiles out of Git. Compiler and MPI modules must match your GEOS build.

## Site command contract

Commands receive the isolated repository as their working directory and execute as argument vectors. Baseline and candidate can select separate CPU/GPU commands and resources. Scripts must not switch back to original checkouts. Build outputs and generated datasets must be ignored by Git, because the patch gate requires clean tracked source after baseline execution. Nested mepo components preserve their relative placement.

* **build** exits zero only after a successful build and configured software tests/sanitizers.
* **run** produces a fresh `dataset` file. It can be the documented finite JSON dataset or NetCDF with the science `netcdf` extra. Include exact experiment metadata, units and aligned coordinates. Weighted conservation requires explicit cell weights; JSON is currently the path for attaching weights.
* **profile** runs the site profiler (for example a configured Nsight or MAPL timing wrapper) and retains output in the job logs or ignored result files.
* **benchmark** runs synchronized compute, excluding queue delay, and writes `{"seconds": 123.45}` to the configured timing file. ATOM removes the previous file before every repetition. Include GPU synchronization and a consistent measured interval in your wrapper. A failed or absent timing is rejected.

Approved scientific diagnostics should include relevant conservation, drift, tendencies and long integrations. The shipped two-field policy is an example, not a GEOS science certification. Hardware, compiler flags, inputs, run length, MPI layout, resolution and timing scope must be controlled and documented before interpreting a speedup.

## Execute and inspect

A prepared proposal uses the `geos_agents.models.PatchProposal` schema. It includes complete new file contents and SHA-256 of each original file. For autonomous generation, configure `nooa_model` (install the `nooa` extra) or a JSON-in/JSON-out `runtime_argv`, and an explicit set of repository/path `targets`. The agent receives source, baseline timing and previous evaluator failures; proposed changes are checked before application.

```bash
atom run --system geos --config geos.local.yaml \
  --target speedup=3 --max-experiments 5 --wall-seconds 86400 \
  --state /your/shared/atom-runs/optimization-01 \
  'Achieve at least 3x GPU acceleration while preserving configured numerical and scientific validity'
atom status GOAL_ID --state /your/shared/atom-runs/optimization-01
atom ledger GOAL_ID --state /your/shared/atom-runs/optimization-01
```

Each command reserves GPUs against the remaining GPU budget before submission. The default budget is 3,600 GPU seconds; use a JSON budget through `--budget` for longer allocations. Queue time counts against the controller wall deadline. Slurm accounting supplies allocation GPU seconds. A benchmark may reserve several sequential allocations, each separately checked.

Completed results are verified on resume. If the controller was killed, inspect the saved `jobs/*/job.json` receipts with `squeue`/`sacct` and cancel or finish outstanding jobs before `--recover-interrupted`. Recovery seals the abandoned attempt and plans a new isolated experiment; it does not assume that a scheduler job stopped when the controller died.

```bash
atom resume GOAL_ID --system geos --config geos.local.yaml \
  --state /your/shared/atom-runs/optimization-01 --recover-interrupted
```

Promotion updates the best-valid-candidate pointer only. It does not merge or push changes to GEOS upstreams. Source commits, proposals, diffs, policies, raw outputs, timing repetitions and evaluator evidence remain in the experiment directory with integrity hashes.

References: [Discover](https://www.nccs.nasa.gov/systems/discover/), [Slurm sbatch](https://slurm.schedmd.com/sbatch.html), [Slurm sacct](https://slurm.schedmd.com/sacct.html).
