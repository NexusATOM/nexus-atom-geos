import sys

import pytest
from nexus_atom_controller import Controller, Store
from nexus_atom_controller.discovery import PluginPlanner
from nexus_atom_core import Budget, CapabilityRegistry, Goal

from nexus_atom_geos.config import GEOSConfig
from nexus_atom_geos.plugin import GEOSPlugin
from nexus_atom_geos.workflows import regression_plan


def regression_plugin(tmp_path, *, prepared=True):
    original = GEOSPlugin.demo(tmp_path / "fixture")
    data = original.config.model_dump()
    data["workflow"] = "regression"
    data["commands"] = {k: v for k, v in data["commands"].items() if k in {"build", "run"}}
    data["benchmark_identity"] = {}
    if not prepared:
        data["proposal"] = None
    return GEOSPlugin(GEOSConfig.model_validate(data))


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["prepared", "repeat", "wrong", "failed-test", "failed-baseline"])
async def test_regression_compares_both_phases_without_performance(tmp_path, case):
    plugin = regression_plugin(tmp_path, prepared=case != "repeat")
    data = plugin.config.model_dump()
    data["software_checks"] = ("test",)
    data["commands"]["test"] = (
        sys.executable,
        "-c",
        "from kernel import compute; assert compute() == 4999950000.0",
    )
    if case == "wrong":
        data["phase_commands"] = {
            "candidate": {
                "run": (
                    sys.executable,
                    "-c",
                    "import run,json; from pathlib import Path; p=Path('results/fields.json'); "
                    "d=json.loads(p.read_text()); d['fields']['synthetic_mass']['values'][0]+=1; "
                    "p.write_text(json.dumps(d))",
                )
            }
        }
    if case in {"failed-test", "failed-baseline"}:
        phase = "baseline" if case == "failed-baseline" else "candidate"
        data["phase_commands"] = {phase: {"test": (sys.executable, "-c", "raise SystemExit(4)")}}
    plugin = GEOSPlugin(GEOSConfig.model_validate(data))
    registry = CapabilityRegistry()
    registry.register(plugin)
    goal = Goal(objective="Check regression", constraints=plugin.goal_constraints())
    store = Store(tmp_path / "state")
    try:
        controller = Controller(
            registry, PluginPlanner(plugin), store, Budget(max_experiments=3, wall_seconds=90)
        )
        state = await controller.run(goal)
        history = store.history(goal.id)
        assert len(history) == 1
        experiment = history[0]
        directory = store.directory(experiment.id)
        assert "geos.performance" not in goal.constraints
        assert not any(
            task.capability in {"geos.profile", "geos.benchmark"} for task in experiment.tasks
        )
        assert (directory / "evidence/baseline-fields.json").is_file() == (
            case != "failed-baseline"
        )
        if case in {"prepared", "repeat"}:
            assert state["status"] == "succeeded"
            assert state["best_valid_candidate"] == experiment.id
            assert (directory / "evidence/candidate-fields.json").is_file()
            assert all(e.passed for e in experiment.evaluations)
            assert (directory / "evidence/proposal.json").exists() == (case == "prepared")
            assert (await controller.run(goal))["status"] == "succeeded"
            assert len(store.history(goal.id)) == 1
        else:
            assert state["status"] != "succeeded"
            assert state["best_valid_candidate"] is None
            if case == "wrong":
                assert not next(
                    e for e in experiment.evaluations if e.evaluator == "geos.numerical"
                ).passed
                assert not next(
                    e for e in experiment.evaluations if e.evaluator == "geos.science"
                ).passed
        assert all(a.verify(directory) for a in experiment.artifacts)
        source = tmp_path / "fixture/baseline/kernel.py"
        assert "for i in range" in source.read_text()
    finally:
        store.close()


@pytest.mark.asyncio
async def test_regression_rejects_generation_and_speedup_targets(tmp_path):
    plugin = regression_plugin(tmp_path)
    with pytest.raises(ValueError, match="prepared proposals"):
        GEOSConfig.model_validate({**plugin.config.model_dump(), "nooa_model": "example/model"})
    with pytest.raises(ValueError, match="does not measure speedup"):
        await plugin.plan(Goal(objective="x", target={"speedup": 3}), (), CapabilityRegistry())
    # A pure Slurm regression does not require a timing file it will never use.
    assert (
        GEOSConfig.model_validate({**plugin.config.model_dump(), "backend": "slurm"}).workflow
        == "regression"
    )
    with pytest.raises(ValueError, match="benchmark"):
        GEOSConfig.model_validate({**plugin.config.model_dump(), "workflow": "modernization"})
    with pytest.raises(ValueError, match="unique"):
        regression_plan(software_checks=("test", "test"))
