# Python API

The top-level package is `geos_agents`; the distribution is `nexus-geos-agent`.
NOOA is required at installation, but offline tools do not import its runtime.

## Inspect and plan offline

```python
import asyncio
from pathlib import Path
from geos_agents.models import GEOSTask, Workflow
from geos_agents.registry import RepositoryRegistry
from geos_agents.workflows import WorkflowRunner

registry = RepositoryRegistry.from_file(Path("examples/demo/workspace.yaml"))
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
compiler-derived Fortran symbol/call graphs. Persistent expert memory, semantic
Fortran/CUDA analysis, native NetCDF comparison, and production scheduler adapters
remain explicit future work.
