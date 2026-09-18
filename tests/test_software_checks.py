import json
import sys

import pytest
from nexus_atom_controller import Controller, Store
from nexus_atom_controller.discovery import PluginPlanner
from nexus_atom_core import Budget, CapabilityRegistry, Goal

from nexus_atom_geos.config import GEOSConfig
from nexus_atom_geos.plugin import GEOSEvaluator, GEOSPlugin
from nexus_atom_geos.workflows import modernization_plan


def configured(tmp_path):
    plugin = GEOSPlugin.demo(tmp_path / "demo")
    data = plugin.config.model_dump()
    data["software_checks"] = ("test", "sanitize")
    data["commands"].update(
        {
            "test": (
                sys.executable,
                "-c",
                "from kernel import compute; assert compute() == 4999950000.0",
            ),
            # Synthetic stand-in for a site's sanitizer runner, not a real sanitizer.
            "sanitize": (sys.executable, "-c", "print('synthetic sanitizer runner completed')"),
            "benchmark": (sys.executable, "-c", "pass"),
            "profile": (sys.executable, "-c", "print('synthetic profile')"),
        }
    )
    plugin.config = GEOSConfig.model_validate(data)
    return plugin


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, ("baseline", "test"), ("candidate", "sanitize")])
async def test_explicit_checks_gate_acceptance(tmp_path, failure):
    plugin = configured(tmp_path)
    if failure:
        phase, check = failure
        data = plugin.config.model_dump()
        data["phase_commands"] = {
            phase: {
                check: (
                    sys.executable,
                    "-c",
                    "import sys; print('check found a defect',file=sys.stderr); sys.exit(3)",
                )
            }
        }
        plugin.config = GEOSConfig.model_validate(data)
    registry = CapabilityRegistry()
    registry.register(plugin)
    store = Store(tmp_path / "state")
    goal = Goal(objective="Require declared software checks", constraints=plugin.goal_constraints())
    state = await Controller(
        registry, PluginPlanner(plugin), store, Budget(max_experiments=1, wall_seconds=90)
    ).run(goal)
    experiment = store.history(goal.id)[0]
    assert {"geos.tests", "geos.sanitizers"} <= set(goal.constraints)
    if failure:
        assert state["status"] != "succeeded"
        assert state["best_valid_candidate"] is None
        result = next(r for r in experiment.results if r.status == "failed")
        assert "check found a defect" in result.outputs["stderr"]["text"]
        path = store.directory(experiment.id) / f"evidence/{failure[0]}-{failure[1]}.json"
        assert json.loads(path.read_text())["returncode"] == 3
    else:
        assert state["status"] == "succeeded"
        assert len(experiment.results) == 16
        assert all(e.passed for e in experiment.evaluations)
        assert (
            len(next(e for e in experiment.evaluations if e.evaluator == "geos.software").evidence)
            == 8
        )
    store.close()


@pytest.mark.asyncio
async def test_custom_plan_cannot_omit_required_check_evidence(tmp_path):
    plugin = configured(tmp_path)
    evidence = tmp_path / "record/evidence"
    evidence.mkdir(parents=True)
    for phase in ("baseline", "candidate"):
        for kind in ("build", "run", "test"):
            (evidence / f"{phase}-{kind}.json").write_text('{"status":"succeeded"}')
    goal = Goal(objective="x", constraints=plugin.goal_constraints())
    with pytest.raises(FileNotFoundError):
        await GEOSEvaluator(plugin, "software").evaluate(goal, (), evidence.parent)


def test_configuration_and_plan_reject_missing_or_duplicate_checks(tmp_path):
    plugin = configured(tmp_path)
    data = plugin.config.model_dump()
    data["commands"].pop("sanitize")
    with pytest.raises(ValueError, match="required software check"):
        GEOSConfig.model_validate(data)
    with pytest.raises(ValueError, match="unique"):
        modernization_plan(software_checks=("test", "test"))
