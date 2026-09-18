# Optional repository and science-objective specialists

Keep the six built-in roles as the common workflow. Add focused advisory profiles
when a task needs repository-specific knowledge or a science-objective review.
A profile configures `ProfileSpecialistAgent`; it does not create a new service,
change tools, or replace an executed acceptance check. No profiles are enabled by
default. Existing tasks and session databases remain compatible.

## Configure both dimensions

The [example profile file](../examples/legacy/specialists.yaml) includes an
FV3 interface reviewer, a conservation reviewer, and a reproducibility reviewer.
A minimal custom file looks like:

```yaml
specialists:
  - name: fv3-conservation
    repositories: [fvdycore]
    objective_tags: [conservation]
    instructions: >-
      Review source and evidence for conservation assumptions. Identify missing
      units, weights, flux terms, and approved acceptance criteria.
    required_evidence:
      - Reference and candidate outputs with matching units and coordinates
      - Domain-approved conservation policy
```

Selection is deterministic:

- Repository names use the existing registry aliases. A profile sees only the
  matching repositories already selected by the task; it cannot expand selection.
- Any matching `objective_tags` value activates the objective dimension. Tags
  must be explicitly set on the task; they are not guessed from natural language.
- If both filters are supplied, both must match. Empty filters impose no further
  restriction. At least one selected repository must have source evidence.
- An active profile naming an unbound repository fails before model calls.
- At most eight profiles are allowed, with unique names and bounded instructions.
  A profile file is limited to 64 KiB and accepts only the `specialists` key.

`required_evidence` is a review checklist. The agent is instructed to report
missing evidence as unknowns; the list does not itself run checks or enforce
numerical acceptance. Profiles currently receive scoped source context and
available baseline timing evidence. They do not automatically ingest arbitrary
scientific datasets, papers, or external retrieval systems.

## Run and inspect selection

After [setup](READINESS.md), from the GEOS repository root:

```bash
# No credentials: exercise seven real NOOA dispatches with scripted responses.
python examples/legacy/run_agents_demo.py --with-specialists

# No model calls: inspect source and record which profiles would be selected.
geos-agent investigate 'Review the pressure calculation' \
  --workspace examples/legacy/demo/workspace.yaml --repo fvdycore \
  --specialists examples/legacy/specialists.yaml \
  --objective-tag conservation --offline
```

The scripted demo invokes the repository agent, the two matching optional
reviewers, then architecture, CUDA, performance and validation roles. It uses
NOOA's fake client and is not a science or model-quality experiment.
For actual reasoning, replace `--offline` with `--model provider/model`, using
an explicitly configured provider/model. Each selected profile adds a bounded
model call with the workflow's call timeout and NOOA retry policy. Account for
that extra latency and cost; it is not automatically beneficial.

Each run stores `task.json` with the full profile configuration and
`specialists.json` with enabled/selected names and scoped repositories and
measurement IDs. Actual assessments appear as `specialist:NAME` in `result.json`.
Citation checks reject references outside the evidence supplied to that reviewer.
Reviews feed architecture synthesis and, for implementation workflows, bounded
proposal context. The configured build/numerical/science gates remain authoritative.

## Use profiles in sessions and engineering

`--specialists` and repeated `--objective-tag` options are supported by the
reasoning commands, `work`, and `session add`:

```bash
geos-agent session add SESSION_ID 'Review reproducibility requirements' \
  --repo fvdycore --specialists examples/legacy/specialists.yaml \
  --objective-tag reproducibility
```

This is offline unless a model is set on the task. Session creation uses the
normal workspace/objective configuration described in [sessions](legacy/SESSIONS.md).
The task stores profile contents, not just the YAML path: later edits or removal
of that file do not alter a queued task. Profile reviews in `work` require the
live reasoning path; a prepared proposal does not trigger extra model calls.

Python callers can set `GEOSTask(specialists=(SpecialistProfile(...),),
objective_tags=("conservation",), ...)` or use
`geos_agents.specialists.load_specialists(Path(...))`. `WorkflowRunner` and
`GEOSSession` handle the configuration. The built-in runner uses the same model
client for all roles. A custom Python orchestrator can instantiate
`ProfileSpecialistAgent(llm=another_client)` and call `review`, while providing
its own tracing, scope/citation checks, and deadlines.

The ATOM plugin's generic `NOOARuntime` does not automatically run this specialist
workflow. These profiles apply to the GEOS Agent workflow APIs/CLI; an external
orchestrator must call those interfaces or implement an explicit adapter.

## Information that would improve the agents

The next useful step is a small benchmark of representative tasks, not simply
adding more role names. For an initial objective, supply as much of this as is
available:

| Information | Why it matters |
|---|---|
| Repository names, exact commits, key files/interfaces, and known ownership boundaries | Grounds the repository profiles in the actual implementation |
| A few real tasks and examples of useful expert answers or accepted patches | Defines useful behavior and a baseline for evaluation |
| Known failures and rejected changes, with reasons | Tests whether agents detect errors rather than merely generate plausible answers |
| Reference inputs/outputs, units, coordinates, weights, and reproducible run instructions | Makes numerical/scientific evidence interpretable |
| Expert-approved checks, tolerances, and criteria for escalation | Defines acceptance without letting agents invent scientific policy |
| Build/test/profile commands, compiler/MPI/GPU configuration, and Discover resources | Enables comparable execution and bottleneck analysis |
| Chosen model/provider, allowed source-data destinations, and cost/time limits | Makes reasoning experiments controlled and repeatable |

A useful evaluation holds the task, model, source, and acceptance checks fixed
and compares the base workflow with optional specialists enabled. Measure factual
citation errors, reviewer-identified defects, accepted correct changes, failed
runs, redundant work, model usage, and latency. Include unseen tasks and negative
controls such as deliberately wrong numerical output. A specialist is useful
when it improves those outcomes at an acceptable cost, not because it has a
convincing role description.

Likely improvements are richer compiler/profiler and scientific evidence adapters,
expert-reviewed objective profiles, a curated failure/regression corpus, and
scoped reusable findings that are revalidated against current source. Existing
sessions already retain findings and decisions; this is not automatic model
training. Live-provider quality, real GEOS gains, and scientific validity remain
to be measured with the supplied cases.
