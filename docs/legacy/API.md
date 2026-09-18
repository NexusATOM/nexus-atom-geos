# Python API

> These supported GEOS Agent interfaces now live in `nexus-atom-geos`. Follow
> [installation](../READINESS.md), activate that environment, and run commands
> from the repository root. The `legacy` directory records their origin; it
> does not require installing the old standalone distribution.

The top-level package is `geos_agents`; the distribution is `nexus-atom-geos`.
NOOA is required at installation, but offline tools do not import its runtime.

## Inspect and plan offline

```python
import asyncio
from pathlib import Path
from geos_agents.models import GEOSTask, Workflow
from geos_agents.registry import RepositoryRegistry
from geos_agents.workflows import WorkflowRunner

registry = RepositoryRegistry.from_file(Path("examples/legacy/demo/workspace.yaml"))
runner = WorkflowRunner(registry, Path(".geos-agent/runs"))
result = asyncio.run(runner.execute(GEOSTask(
    description="Port pressure_log to CUDA",
    workflow=Workflow.GPU_PORT,
    repositories=("fvdycore",),
)))
print(result.status, result.scientific_validation)
```

## Use real NOOA agents

```python
from nooa.unifiedllm.registry import get_llm_client
from geos_agents.agents import GEOSAgent

# The provider's credentials must already be configured in the environment.
llm = get_llm_client("provider/model")
agent = GEOSAgent(runner, llm=llm)
result = asyncio.run(agent.solve(GEOSTask(description="Explain MAPL fields", repositories=("MAPL",))))
```

Tests inject `nooa.unifiedllm.FakeLLMClient` with scripted JSON responses through
the same Agent/PredictStrategy execution path. There is no alternate home-grown
LLM adapter pretending to be NOOA. Each specialist is instantiated on demand;
repository specialists do not share conversation state.

## Execute the engineering process

```python
import yaml
from geos_agents.engineering import EngineeringPolicy, EngineeringRunner

policy = EngineeringPolicy.model_validate(yaml.safe_load(Path("site-policy.yaml").read_text()))
engineering = EngineeringRunner(registry, Path(".geos-agent/runs"))
report = asyncio.run(engineering.work(
    GEOSTask(description="Make the requested change", repositories=("fvdycore",)),
    policy,
    execute=True,
    llm=llm,
    targets=(("fvdycore", "actual/path/to/source.F90"),),
))
```

Supply either a model or a `PatchProposal`, never both. Prepared proposals allow
deterministic execution without model access. `GEOSWorkspace` composes repository
bindings, bounded context, named commands and artifacts. Add scheduler/site behavior
through explicit wrapper commands rather than giving an LLM arbitrary shell access.

## Extend the system

- Bind additional repositories in workspace YAML; select uncatalogued ones explicitly.
- Add catalog domain hints only after inspecting the actual upstream project.
- Add typed NOOA prediction methods for reasoning, retaining evidence references.
- Add deterministic tools for parsers, domain-specific scientific checks or native
  file exporters; test their failure semantics separately from agent text.
- Preserve `not_certified` for scientific claims unless a separate, domain-approved
  certification process exists. A zero process exit code alone cannot establish science.

`ContextLoader.read_file()` returns complete bounded text plus SHA-256;
`load()` returns lexical excerpts with Git and line provenance. These are not
compiler-derived Fortran symbol/call graphs. Semantic Fortran/CUDA analysis,
native NetCDF comparison, and production scheduler adapters
remain explicit future work.

## Persist and resume a session

```python
from geos_agents.sessions import GEOSSession, SessionRequest, SessionStore

with SessionStore(Path(".geos-agent/sessions.sqlite3")) as store:
    session_id = store.create("Understand MAPL field ownership", registry)
    first = store.add(session_id, SessionRequest(task=GEOSTask(
        description="Inspect MAPL fields", repositories=("MAPL",))))
    store.add(session_id, SessionRequest(task=GEOSTask(
        description="Explain the field interface", repositories=("MAPL",))),
        depends_on=(first,), parent=first)
    state = asyncio.run(GEOSSession(store, session_id).run_pending(max_tasks=1))

# Reopening uses SQLite state rather than reconstructing chat history.
with SessionStore(Path(".geos-agent/sessions.sqlite3")) as store:
    state = asyncio.run(GEOSSession(store, session_id).run_pending())
```

Set `SessionRequest.model` for live NOOA reasoning. An engineering request has
`kind="work"`, a validated `EngineeringPolicy`, and optional explicit execution
authorization. Policies/proposals are saved as typed values, not mutable references
to external config files. Workspace command definitions are snapshotted when a
session is created. Tests may supply `run_pending(llm_factory=...)` for scripted
NOOA clients without network or credentials.
