import pytest
from nexus_atom_controller import Controller, Store
from nexus_atom_controller.discovery import PluginPlanner
from nexus_atom_core import Budget, CapabilityRegistry, Goal

from nexus_atom_geos.examples import ECCOExample, ISSMExample, LISExample, ModelEExample
from nexus_atom_geos.plugin import GEOSPlugin


@pytest.mark.asyncio
async def test_complete_synthetic_modernization(tmp_path):
    plugin = GEOSPlugin.demo(tmp_path / "demo")
    commands = dict(plugin.config.commands)
    profile = commands.pop("profile")
    plugin.config = plugin.config.model_copy(
        update={"commands": commands, "phase_commands": {"baseline": {"profile": profile}}}
    )
    registry = CapabilityRegistry()
    registry.register(plugin)
    store = Store(tmp_path / "state")
    goal = Goal(
        objective="Optimize synthetic kernel",
        system="geos",
        constraints=plugin.goal_constraints(),
        target={"speedup": 1},
    )
    result = await Controller(registry, PluginPlanner(plugin), store, Budget(wall_seconds=120)).run(
        goal
    )
    history = store.history(goal.id)
    assert result["status"] == "succeeded", [
        (e.status, [r.error for r in e.results], e.evaluations) for e in history
    ]
    assert len(history[0].results) == 12
    assert (store.directory(history[0].id) / "evidence/candidate-profile.json").is_file()
    import csv
    import json

    for phase in ("baseline", "candidate"):
        evidence = store.directory(history[0].id) / "evidence"
        with (evidence / f"{phase}-timings.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        samples = json.loads((evidence / f"{phase}-benchmark.json").read_text())["samples"]
        assert [float(row["seconds"]) for row in rows] == samples
        assert all(row["phase"] == phase for row in rows)
    assert "for i in range" in (tmp_path / "demo/baseline/kernel.py").read_text()
    assert len(history[0].artifacts) > 10
    store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("factory", [ECCOExample, LISExample, ISSMExample, ModelEExample])
async def test_other_model_examples(tmp_path, factory):
    plugin = factory()
    registry = CapabilityRegistry()
    registry.register(plugin)
    store = Store(tmp_path / "state")
    goal = Goal(
        objective="Demonstrate contract", system=plugin.name, constraints=plugin.goal_constraints()
    )
    assert (await Controller(registry, PluginPlanner(plugin), store).run(goal))[
        "status"
    ] == "succeeded"
    store.close()


@pytest.mark.asyncio
async def test_bad_patch_cannot_be_promoted(tmp_path):
    import json

    plugin = GEOSPlugin.demo(tmp_path / "demo")
    proposal = plugin.config.proposal
    data = json.loads(proposal.read_text())
    data["changes"][0]["content"] = "def compute():\n    return -1.0\n"
    proposal.write_text(json.dumps(data))
    registry = CapabilityRegistry()
    registry.register(plugin)
    store = Store(tmp_path / "state")
    goal = Goal(objective="reject invalid optimization", constraints=plugin.goal_constraints())
    result = await Controller(registry, PluginPlanner(plugin), store, Budget(wall_seconds=120)).run(
        goal
    )
    assert result["status"] == "no_more_plans"
    assert result["best_valid_candidate"] is None
    assert store.history(goal.id)[0].status == "rejected"
    store.close()
