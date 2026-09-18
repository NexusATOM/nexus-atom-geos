import json
from types import SimpleNamespace

import pytest
from nexus_atom_core import Artifact, ExecutionContext, Goal, Task

from nexus_atom_geos.plugin import GEOSPlugin


@pytest.mark.asyncio
async def test_failed_validation_retains_configured_plot_evidence(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    plugin = GEOSPlugin.demo(tmp_path / "demo")
    plugin.config = plugin.config.model_copy(update={"plot_fields": ("synthetic_mass",)})
    monkeypatch.setattr(
        plugin,
        "_workspace",
        lambda context: SimpleNamespace(get=lambda name: SimpleNamespace(path=tmp_path)),
    )
    directory = tmp_path / "experiment"
    evidence = directory / "evidence"
    evidence.mkdir(parents=True)
    for phase, value in (("baseline", 1), ("candidate", 2)):
        (evidence / f"{phase}-fields.json").write_text(
            json.dumps(
                {
                    "fields": {
                        "synthetic_mass": {
                            "units": "1",
                            "shape": [1],
                            "values": [value],
                            "weights": [1],
                        }
                    }
                }
            )
        )
    task = Task(capability="geos.validate")
    result = await plugin.execute(
        "validate",
        task,
        ExecutionContext(
            goal=Goal(objective="Compare fields", constraints=plugin.goal_constraints()),
            experiment_id="example",
            directory=directory,
        ),
    )
    assert result.status == "failed"
    assert not all(e["passed"] for e in result.outputs["evaluations"])
    manifest = json.loads((evidence / "plots.json").read_text())
    artifact = Artifact.model_validate(manifest["synthetic_mass"])
    assert artifact.kind == "plot" and artifact.verify(directory)
    assert (directory / artifact.path).read_bytes().startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_controller_seals_comparison_plots(tmp_path):
    import sys

    from nexus_atom_controller import Controller, Store
    from nexus_atom_controller.discovery import PluginPlanner
    from nexus_atom_core import Budget, CapabilityRegistry

    from nexus_atom_geos.config import GEOSConfig

    pytest.importorskip("matplotlib")
    plugin = GEOSPlugin.demo(tmp_path / "demo")
    data = plugin.config.model_dump()
    data["plot_fields"] = ("synthetic_mass",)
    data["commands"]["benchmark"] = (sys.executable, "-c", "pass")
    plugin = GEOSPlugin(GEOSConfig.model_validate(data))
    registry = CapabilityRegistry()
    registry.register(plugin)
    store = Store(tmp_path / "state")
    try:
        goal = Goal(objective="Record scientific plots", constraints=plugin.goal_constraints())
        await Controller(
            registry, PluginPlanner(plugin), store, Budget(max_experiments=1, wall_seconds=90)
        ).run(goal)
        experiment = store.history(goal.id)[0]
        directory = store.directory(experiment.id)
        paths = {str(a.path) for a in experiment.artifacts}
        assert "evidence/plots/field-0000.png" in paths
        assert "evidence/plots.json" in paths
        assert all(a.verify(directory) for a in experiment.artifacts)
        (directory / "evidence/plots/field-0000.png").write_bytes(b"changed")
        with pytest.raises(ValueError, match="[Aa]rtifact"):
            store.history(goal.id)
    finally:
        store.close()
