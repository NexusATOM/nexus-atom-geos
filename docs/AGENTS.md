# How to use and orchestrate the GEOS agents

There are six NOOA agent classes. Five provide specialist reasoning and the sixth,
`GEOSAgent`, invokes a bounded workflow. They are composable Python objects;
they are not six background services or six separate model providers. The default
workflow invokes selected specialists sequentially with the same model client.

## Agents available today

| Agent | Methods | Inputs and purpose |
|---|---|---|
| `RepositoryAgent` | `investigate`, `propose` | Analyze bounded source evidence; propose complete replacement contents for explicitly selected files |
| `ArchitectureAgent` | `synthesize` | Combine repository assessments and evidence across the GEOS federation |
| `CUDAAgent` | `plan` | Assess GPU porting issues such as precision, data layout, transfers and halos |
| `PerformanceAgent` | `plan`, `diagnose` | Propose measurements, or interpret supplied measured timing evidence |
| `ValidationAgent` | `review` | Identify gaps in a proposed software/numerical/scientific validation plan |
| `GEOSAgent` | `solve` | Delegate a task to `WorkflowRunner` using its NOOA client |

Specialists return typed `Assessment` objects; `propose` returns `PatchProposal`.
Pydantic validates those records. NOOA's `PredictStrategy` performs the reasoning
calls. Source findings must cite supplied evidence IDs; the workflow checks those
references. A `ValidationAgent` review does **not** execute tests or certify science.

## Try the orchestration without API keys

Install this repository with the `nooa` extra following [setup](READINESS.md), activate
the workspace environment, and run from the `nexus-atom-geos` repository root:

```bash
python examples/legacy/run_agents_demo.py
```

The demo uses NOOA's actual agent dispatch with five scripted `FakeLLMClient`
responses. It prints the specialist sequence and paths to `result.json` and the
trace. It makes no provider calls and executes no model; it shows how the pieces
connect. The five calls are Repository → Architecture → CUDA → Performance →
Validation. `GEOSAgent` coordinates them without an extra generation call.

For ordinary source inspection without any reasoning calls:

```bash
geos-agent investigate 'Trace pressure_log' \
  --workspace examples/legacy/demo/workspace.yaml --repo fvdycore --offline
```

## Use a live model

Configure the chosen provider's credentials in the environment and replace
`provider/model` with an actual model identifier supported by your NOOA setup:

```bash
geos-agent gpu-port 'Assess a CUDA port of pressure_log' \
  --workspace examples/legacy/demo/workspace.yaml --repo fvdycore \
  --model provider/model --call-timeout 120 --context-chars 24000
```

This performs reasoning over the synthetic source fixture. For actual GEOS, use
`geos-agent init --mepo /path/to/GEOSgcm --output workspace.local.yaml` and select
the relevant repositories from that profile. `investigate` and `explain` use
repository, architecture and validation reasoning; `gpu-port` additionally uses
CUDA and performance planning. `implement` proposes edits to explicit `--file
REPOSITORY:path` targets; GPU/CUDA tasks also invoke the relevant specialists.
Without `--model`, these workflows inventory evidence rather than call a model.

The workflow passes repository reports to architecture synthesis and bounded
assessment summaries to code proposals. It does not pass every agent's private
chat history to every other agent. GPU and validation specialists primarily
receive the task and source contexts. Measurements supplied by the engineering
workflow can trigger performance diagnosis instead of a measurement plan.

## Call an agent from your own orchestrator

This complete Python example shows explicit evidence gathering, two specialists,
and citation checks. It calls a live provider when run:

```python
import asyncio
from pathlib import Path
from nooa.unifiedllm.registry import get_llm_client
from geos_agents.agents import ArchitectureAgent, RepositoryAgent
from geos_agents.context import ContextLoader
from geos_agents.models import GEOSTask
from geos_agents.registry import RepositoryRegistry
from geos_agents.workflows import check_citations

async def main():
    registry = RepositoryRegistry.from_file(Path("examples/legacy/demo/workspace.yaml"))
    task = GEOSTask(description="Explain pressure_log", repositories=("fvdycore",))
    context = ContextLoader(registry, max_chars=24000).load("fvdycore", task.description)
    client = get_llm_client("provider/model")
    report = await asyncio.wait_for(
        RepositoryAgent(llm=client).investigate(task, context), timeout=120)
    check_citations(report, (context,))
    synthesis = await asyncio.wait_for(
        ArchitectureAgent(llm=client).synthesize(
            task, (context,), {context.repository: report}), timeout=120)
    check_citations(synthesis, (context,))
    print(synthesis.model_dump_json(indent=2))

asyncio.run(main())
```

Each agent accepts its own `llm` client, so a custom Python orchestrator can use
different models for different roles. The current CLI has one `--model` per
workflow; it does not offer per-specialist model configuration. When invoking
specialists directly, your orchestrator owns deadlines, tracing, persistence,
citation checking, and proposal validation. `WorkflowRunner` supplies those
workflow checks and traces when you use its existing paths.

## Tools and execution

Agents reason over evidence; ordinary Python tools perform the work. The current
specialists do not dynamically discover or invoke arbitrary shell/MCP tools.
An orchestrator selects the tools and decides which results to supply as context.

| Tool/API | Work it performs |
|---|---|
| `RepositoryRegistry` | Bind GEOS/mepo components to local checkouts and named commands |
| `ContextLoader` | Search/read bounded source with Git, line, and hash provenance |
| `PatchManager` | Review/apply proposals with source hash and path checks |
| `CommandRunner` | Run named configured commands with deadlines and output limits |
| `EngineeringRunner` | Manage baseline/candidate worktrees, gates, numerical comparison, benchmarks and reports |
| `SessionStore` / `GEOSSession` | Save objectives/tasks/evidence and execute pending session work |

For example, add a profiler or test runner as a named command in a workspace
profile (replace the paths and arguments with your site's commands):

```yaml
repositories:
  - name: MAPL
    path: /path/to/MAPL
    commands:
      unit-tests:
        argv: [ctest, --test-dir, build, --output-on-failure]
        purpose: test
        timeout_seconds: 600
```

```bash
# Review the resolved command, then execute it explicitly.
geos-agent run MAPL unit-tests --workspace workspace.local.yaml
geos-agent run MAPL unit-tests --workspace workspace.local.yaml --execute
```

Named `run` executes in the bound checkout. For proposed changes, use `work` so
commands run in isolated baseline/candidate worktrees under the configured policy.
`python examples/legacy/run_engineering_demo.py` is the working no-key example of
that complete lifecycle. See [agent CLI usage](legacy/USAGE.md) for `work`, patch and benchmark
commands, and [agent site integration](legacy/SITE-INTEGRATION.md) for GEOS wrappers.

To add a new parser, profiler, or scientific check, implement a deterministic
adapter returning structured evidence, configure/invoke it from the workflow,
and pass its output to the appropriate specialist. Add an executed gate for any
result that should affect acceptance. Adding an agent prompt alone does not
connect a tool or create an acceptance check.

## Save and resume orchestrated work

```bash
geos-agent session create --workspace examples/legacy/demo/workspace.yaml \
  --objective 'Understand GEOS dynamics'
# Replace SESSION_ID with the returned ID.
geos-agent session add SESSION_ID 'Inspect pressure_log' --repo fvdycore
geos-agent session run SESSION_ID
geos-agent resume SESSION_ID --status-only
geos-agent session verify SESSION_ID
```

These commands run offline unless a model is explicitly configured on the task.
Session tasks support dependencies and structured historical context. See
[sessions](legacy/SESSIONS.md) for dependency flags, model selection, recovery, and
engineering tasks. A session is a queue of workflow requests, not a persisted
live agent object or an automatic all-to-all agent conversation.

## Orchestration with NexusATOM

The [ATOM Agents package](https://github.com/NexusATOM/nexus-atom-agents/blob/main/docs/USAGE.md)
provides NOOA/OpenAI/local proposal backends and `AgentRouter` for explicit
capability-to-backend routing. These backends are distinct from the six GEOS
specialist roles. The [ATOM Controller](https://github.com/NexusATOM/nexus-atom-controller)
plans and executes registered capabilities, while evaluators assess recorded
results. Selecting ATOM's generic NOOA backend does not automatically invoke
all six GEOS specialists.

This repository is the canonical home for both interfaces: `geos_agents` provides
the specialist agents and `geos-agent` CLI, while `nexus_atom_geos` supplies the
ATOM plugin. You can use the agent CLI without running Controller. Do not install
the old `nexus-geos-agent` distribution alongside this package: it owns the same
import/CLI names. Existing agent session databases remain the same format;
Controller experiment stores are a separate interface. No bridge to another
team's orchestrator is yet tested. See [readiness](READINESS.md) and
[migration coverage](MIGRATION.md).
