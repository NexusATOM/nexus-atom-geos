import json
from pathlib import Path

import pytest

from geos_agents.models import Assessment, GEOSTask, SpecialistProfile, TimingEvidence
from geos_agents.registry import RepositoryRegistry
from geos_agents.specialists import load_specialists, select_specialists
from geos_agents.workflows import WorkflowRunner

DEMO = Path(__file__).resolve().parents[1] / "examples/legacy/demo/workspace.yaml"


@pytest.fixture(autouse=True)
def offline_costs(monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")


def test_profiles_filter_by_repo_and_objective_without_expanding_context(tmp_path):
    runner = WorkflowRunner(RepositoryRegistry.from_file(DEMO), tmp_path)
    contexts = tuple(runner.loader.load(name, "pressure") for name in ("fvdycore", "MAPL"))
    profiles = (
        SpecialistProfile(
            name="repo-review", instructions="Review source", repositories=("fvdycore",)
        ),
        SpecialistProfile(
            name="science-review", instructions="Review criteria", objective_tags=("conservation",)
        ),
        SpecialistProfile(
            name="combined",
            instructions="Review both",
            repositories=("MAPL",),
            objective_tags=("conservation",),
        ),
        SpecialistProfile(
            name="other-objective", instructions="Review other", objective_tags=("restart",)
        ),
    )
    task = GEOSTask(description="Review", objective_tags=("conservation",), specialists=profiles)
    measurements = tuple(
        TimingEvidence(
            id=f"timing:{name}",
            repository=name,
            command="benchmark",
            median_seconds=1,
            min_seconds=1,
            max_seconds=1,
            trials=2,
            environment={},
        )
        for name in ("fvdycore", "MAPL")
    )
    selected = select_specialists(task, runner.registry, contexts[:1], measurements)
    assert [row[0].name for row in selected] == ["repo-review", "science-review"]
    assert all(row[1] == contexts[:1] for row in selected)
    assert all(row[2] == measurements[:1] for row in selected)
    with pytest.raises(ValueError, match="unique"):
        GEOSTask(description="x", specialists=(profiles[0], profiles[0]))
    with pytest.raises(ValueError):
        GEOSTask(description="x", objective_tags=("not a tag",))


@pytest.mark.asyncio
async def test_profile_real_nooa_dispatch_and_scoped_citation_rejection(tmp_path):
    from nooa.unifiedllm import FakeLLMClient

    registry = RepositoryRegistry.from_file(DEMO)
    runner = WorkflowRunner(registry, tmp_path)
    task = GEOSTask(
        description="Inspect pressure",
        repositories=("fvdycore", "MAPL"),
        specialists=(
            SpecialistProfile(
                name="fv3", instructions="Review precision", repositories=("fvdycore",)
            ),
        ),
    )
    response = Assessment(summary="Scripted review", findings=()).model_dump_json()
    client = FakeLLMClient.with_code_responses([response] * 5)
    result = await runner.execute(task, llm=client)
    assert client.call_count == 5  # two repository, one profile, architecture, validation
    assert "specialist:fv3" in result.assessments
    selection = json.loads((runner.last_trace.directory / "specialists.json").read_text())
    assert selection["selected"][0]["repositories"] == ["GFDL_atmos_cubed_sphere"]
    assert result.scientific_validation == "not_run"

    other = runner.loader.load("MAPL", task.description).evidence[0].id
    invalid = Assessment(
        summary="Out-of-scope citation",
        findings=({"summary": "wrong scope", "evidence_ids": (other,)},),
    )
    client = FakeLLMClient.with_code_responses([response, response, invalid.model_dump_json()])
    with pytest.raises(ValueError, match="unavailable evidence"):
        await runner.execute(task, llm=client)
    assert client.call_count == 3
    assert not (runner.last_trace.directory / "result.json").exists()


def test_cli_snapshots_profiles_and_resumes_without_profile_file(tmp_path, capsys):
    from geos_agents.cli import main
    from geos_agents.sessions import SessionStore

    config = tmp_path / "profiles.yaml"
    config.write_text(
        "specialists:\n  - name: conservation\n    instructions: Review missing criteria\n    objective_tags: [conservation]\n"
    )
    db = tmp_path / "sessions.sqlite3"
    args = ["--db", str(db)]
    assert (
        main(["session", "create", "--workspace", str(DEMO), "--objective", "Review", *args]) == 0
    )
    sid = json.loads(capsys.readouterr().out)["session_id"]
    assert (
        main(
            [
                "session",
                "add",
                sid,
                "Inspect pressure",
                "--repo",
                "fvdycore",
                "--specialists",
                str(config),
                "--objective-tag",
                "conservation",
                *args,
            ]
        )
        == 0
    )
    capsys.readouterr()
    config.unlink()
    assert main(["session", "run", sid, *args]) == 0
    capsys.readouterr()
    with SessionStore(db) as store:
        state = store.snapshot(sid)
        request = state.tasks[0].request
        assert request.task.specialists[0].name == "conservation"
        assert request.task.objective_tags == ("conservation",)
        assert state.tasks[0].status == "completed"
        assert not store.verify(sid)
    assert main(["resume", sid, "--status-only", *args]) == 0


def test_profile_file_rejects_unknown_fields_and_excess_size(tmp_path):
    config = tmp_path / "profiles.yaml"
    config.write_text("specialists: []\ncommands: []\n")
    with pytest.raises(ValueError, match="only a specialists list"):
        load_specialists(config)
    config.write_text(" " * 65537)
    with pytest.raises(ValueError, match="64 KiB"):
        load_specialists(config)


@pytest.mark.asyncio
async def test_unknown_active_repository_rejected_before_model_calls(tmp_path):
    from nooa.unifiedllm import FakeLLMClient

    runner = WorkflowRunner(RepositoryRegistry.from_file(DEMO), tmp_path)
    client = FakeLLMClient()
    task = GEOSTask(
        description="pressure",
        repositories=("fvdycore",),
        specialists=(
            SpecialistProfile(
                name="bad-binding", instructions="Review", repositories=("unknown-model",)
            ),
        ),
    )
    with pytest.raises(ValueError, match="not bound"):
        await runner.execute(task, llm=client)
    assert client.call_count == 0
