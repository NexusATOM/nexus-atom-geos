import json
from pathlib import Path

import pytest

from geos_agents.models import Assessment, GEOSTask, Workflow
from geos_agents.registry import RepositoryRegistry
from geos_agents.workflows import WorkflowRunner

DEMO = Path(__file__).resolve().parents[2] / "examples/legacy/demo/workspace.yaml"


@pytest.fixture(autouse=True)
def local_litellm(monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")


async def test_offline_workflow_writes_replayable_evidence(tmp_path):
    runner = WorkflowRunner(RepositoryRegistry.from_file(DEMO), tmp_path)
    result = await runner.execute(
        GEOSTask(description="Port pressure_log to CUDA", workflow=Workflow.GPU_PORT)
    )
    assert result.status == "planned"
    assert result.mode == "offline"
    assert result.repositories == ("GFDL_atmos_cubed_sphere",)
    assert result.scientific_validation == "not_run"
    saved = json.loads((runner.last_trace.directory / "result.json").read_text())
    assert saved == result.model_dump(mode="json")
    events = [json.loads(line) for line in runner.last_trace.path.read_text().splitlines()]
    assert any(event["event"] == "context.loaded" for event in events)
    assert all(event["run_id"] == result.run_id for event in events)
    assert any(event["parent_id"] for event in events)


async def test_real_nooa_predict_and_orchestration(tmp_path):
    from nooa import Agent
    from nooa.unifiedllm import FakeLLMClient

    from geos_agents.agents import GEOSAgent

    runner = WorkflowRunner(RepositoryRegistry.from_file(DEMO), tmp_path)
    context = runner.loader.load("fvdycore", "pressure_log CUDA")
    assessment = Assessment(
        summary="Evidence-backed review",
        findings=(
            {
                "summary": "The example computes log of pressure.",
                "evidence_ids": (context.evidence[0].id,),
                "confidence": "observed",
            },
        ),
        unknowns=("No GPU benchmark supplied",),
    )
    llm = FakeLLMClient.with_code_responses([assessment.model_dump_json()] * 5)
    agent = GEOSAgent(runner, llm=llm)
    assert isinstance(agent, Agent)
    result = await agent.solve(
        GEOSTask(
            description="pressure_log CUDA", workflow=Workflow.GPU_PORT, repositories=("fvdycore",)
        )
    )
    assert llm.call_count == 5
    assert result.mode == "nooa"
    assert set(result.assessments) == {
        "GFDL_atmos_cubed_sphere",
        "architecture",
        "cuda",
        "performance",
        "validation",
    }
    assert result.assessments["cuda"].findings[0].evidence_ids == (context.evidence[0].id,)
    assert "log_pressure" in json.dumps(llm.last_messages)
    assert context.evidence[0].sha256 in json.dumps(llm.last_messages)


async def test_hallucinated_citation_is_rejected_and_traced(tmp_path):
    from nooa.unifiedllm import FakeLLMClient

    runner = WorkflowRunner(RepositoryRegistry.from_file(DEMO), tmp_path)
    llm = FakeLLMClient.simple_message(
        json.dumps(
            {
                "summary": "made up",
                "findings": [{"summary": "not observed", "evidence_ids": ["nonexistent"]}],
            }
        )
    )
    with pytest.raises(ValueError, match="unavailable evidence"):
        await runner.execute(GEOSTask(description="CUDA"), llm=llm)
    events = [json.loads(line) for line in runner.last_trace.path.read_text().splitlines()]
    assert events[-1]["event"] == "workflow.failed"
    assert not (runner.last_trace.directory / "result.json").exists()


async def test_no_evidence_does_not_call_model(tmp_path):
    from nooa.unifiedllm import FakeLLMClient

    runner = WorkflowRunner(RepositoryRegistry(), tmp_path)
    llm = FakeLLMClient()
    result = await runner.execute(GEOSTask(description="inspect"), llm=llm)
    assert result.status == "needs_context"
    assert llm.call_count == 0


def test_cli_offline(tmp_path, capsys):
    from geos_agents.cli import main

    assert (
        main(
            [
                "gpu-port",
                "pressure_log CUDA",
                "--workspace",
                str(DEMO),
                "--output",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["mode"] == "offline"
    assert main(["inspect", "nonexistent", "--workspace", str(DEMO)]) == 2
