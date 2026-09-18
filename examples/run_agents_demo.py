"""Show five specialist calls through real NOOA with scripted, offline replies."""

import argparse
import asyncio
import json
import os
from pathlib import Path

# Avoid a provider-cost-map network fetch in this explicitly offline example.
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

from nooa.unifiedllm import FakeLLMClient

from geos_agents.agents import GEOSAgent
from geos_agents.models import Assessment, GEOSTask, Workflow
from geos_agents.registry import RepositoryRegistry
from geos_agents.workflows import WorkflowRunner


async def main(output: Path):
    registry = RepositoryRegistry.from_file(Path(__file__).parent / "demo/workspace.yaml")
    runner = WorkflowRunner(registry, output)
    labels = ("repository", "architecture", "cuda", "performance", "validation")
    responses = [
        Assessment(
            summary=f"Scripted {label} reply: demonstrates orchestration only.",
            unknowns=("No live reasoning, model execution or science verification performed.",),
        ).model_dump_json()
        for label in labels
    ]
    client = FakeLLMClient.with_code_responses(responses)
    result = await GEOSAgent(runner, llm=client).solve(
        GEOSTask(
            description="Inspect pressure_log for a possible CUDA port",
            workflow=Workflow.GPU_PORT,
            repositories=("fvdycore",),
        )
    )
    assert client.call_count == 5
    assert len(result.assessments) == 5
    assert result.scientific_validation == "not_run"
    events = [json.loads(line) for line in runner.last_trace.path.read_text().splitlines()]
    print(
        json.dumps(
            {
                "specialists": [
                    event["data"]["specialist"]
                    for event in events
                    if event["event"] == "delegation.result"
                ],
                "provider_calls": 0,
                "nooa_scripted_calls": client.call_count,
                "result": str(runner.last_trace.directory / "result.json"),
                "trace": str(runner.last_trace.path),
                "note": "Real NOOA dispatch with scripted responses; no live reasoning or GEOS run.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".geos-agent/agent-demo"))
    asyncio.run(main(parser.parse_args().output))
