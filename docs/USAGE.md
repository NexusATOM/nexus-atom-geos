# Usage

## Install and smoke test

Use Python 3.12 or 3.13:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
geos-agent catalog
geos-agent gpu-port 'Port pressure_log to CUDA' \
  --workspace examples/demo/workspace.yaml --offline
```

Offline mode never imports the model runtime and never performs model inference.
It emits an evidence inventory and deterministic validation plan, not a simulated
LLM answer. The demo source is synthetic and clearly labeled as such.

## Bind a real GEOS checkout

For an existing mepo-managed GEOSgcm fixture:

```bash
geos-agent init --mepo /work/GEOSgcm --output workspace.local.yaml
geos-agent graph --workspace workspace.local.yaml
geos-agent inspect fvdycore --query 'epv' --workspace workspace.local.yaml
```

`init` reads the local `components.yaml`, preserving literal `@` directories and
expected tags. It binds catalogued components only and never clones or builds
anything. Missing checkouts are recorded as missing context. `expected_ref` is a
manifest declaration; it is not a claim that the checkout matches that tag.
Each context separately records the observed Git commit, branch and dirty state.

Alternatively write a profile:

```yaml
repositories:
  - name: GEOSgcm
    path: /work/GEOSgcm
  - name: GFDL_atmos_cubed_sphere
    path: /work/GEOSgcm/src/Components/@GEOSgcm_GridComp/GEOSagcm_GridComp/GEOSsuperdyn_GridComp/@FVdycoreCubed_GridComp/@fvdycore
  - name: MAPL
    path: /work/GEOSgcm/src/Shared/@MAPL
```

Relative paths resolve against the profile location, not the caller's directory.
`GEOSfvdycore` and `fvdycore` resolve to `GFDL_atmos_cubed_sphere`.

## Reason with NOOA

Set the credential environment variables required by your chosen NOOA/LiteLLM
provider. The library does not embed credentials or choose a paid model for you.
Pass a model name explicitly (substitute your provider/model below):

```bash
geos-agent investigate 'Where does EPV enter the dynamics wrapper?' \
  --workspace workspace.local.yaml \
  --repo GFDL_atmos_cubed_sphere --repo FVdycoreCubed_GridComp \
  --model provider/model

geos-agent gpu-port 'Port the D-grid EPV calculation to CUDA' \
  --workspace workspace.local.yaml --repo fvdycore --repo FVdycoreCubed_GridComp \
  --constraint exact-numerics --model provider/model
```

Without `--model` the workflow runs offline. `--repo` is repeatable and recommended
for scientific tasks; automatic routing uses catalog keywords, not semantic
retrieval. `--max-repos` defaults to 3 (maximum 8). Each repository has a 24,000
source-character budget, adjustable with `--context-chars`; source scans also
have file/count/byte limits. Large files and excluded directories may be missed.
Use the Python ContextLoader API to adjust scan limits.

Per-repository NOOA agents receive isolated context. ArchitectureAgent synthesizes
their findings. GPU workflows add CUDAAgent and PerformanceAgent. ValidationAgent
reviews validation gaps. Each generation method has two schema-validation attempts
and a 120-second outer timeout (configurable via `--call-timeout`). This is not a
dollar/token budget; provider retries and billing still follow provider behavior.
The default workflow uses PredictStrategy structured output, not CodeAct execution.

## Propose an implementation

```bash
geos-agent implement 'Add the requested numerical guard and document its assumptions' \
  --workspace workspace.local.yaml --repo fvdycore \
  --file fvdycore:relative/path/to/source.F90 --model provider/model
```

Provide actual paths discovered by inspection. Only explicit `--file` targets may
be changed. Existing targets are read in full (bounded to 256 KiB each and 96,000
characters total); a nonexistent target represents an explicitly requested new
file. The output `proposal.json` contains complete replacements and original file
SHA-256 digests. No edits are applied by this workflow. A missing or partial context
can lead to an empty proposal rather than a fabricated implementation.

## Inspect results

Each run produces `task.json`, `contexts.json`, `events.jsonl`, and `result.json`;
implementation runs can also produce `proposal.json`. JSONL events carry schema
version, run/event IDs, parent span, UTC timestamp, and typed event data. Failed
stages are recorded, and failure does not produce a successful result artifact.
`--json` writes the structured result to stdout. Source excerpts and proposed
content are stored locally: treat the output directory like your source checkout.

All workflow results explicitly report scientific validation as `not_run`.
Successful generation means a typed, citation-checked response, not proof that
the conclusions or proposed implementation are correct.
