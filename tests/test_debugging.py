import hashlib
import json
import subprocess
import sys

import pytest
from nexus_atom_controller import Controller, Store
from nexus_atom_controller.discovery import PluginPlanner
from nexus_atom_core import Budget, CapabilityRegistry, Goal

from nexus_atom_geos.config import GEOSConfig
from nexus_atom_geos.plugin import GEOSPlugin


def debug_plugin(tmp_path, case="valid"):
    plugin = GEOSPlugin.demo(tmp_path / "fixture")
    root = tmp_path / "fixture/baseline"
    kernel = root / "kernel.py"
    if case != "healthy":
        kernel.write_text("def compute():\n    return -1.0\n")
        subprocess.run(["git", "-C", str(root), "add", "kernel.py"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Demo",
                "-c",
                "user.email=demo@example.invalid",
                "commit",
                "-qm",
                "Synthetic bug",
            ],
            check=True,
        )
    proposal = json.loads(plugin.config.proposal.read_text())
    proposal["changes"][0]["before_sha256"] = hashlib.sha256(kernel.read_bytes()).hexdigest()
    if case == "bad-repair":
        proposal["changes"][0]["content"] = "def compute():\n    return -2.0\n"
    if case == "harness-edit":
        proposal["changes"].append(
            {
                "repository": "MAPL",
                "path": "run.py",
                "before_sha256": hashlib.sha256((root / "run.py").read_bytes()).hexdigest(),
                "content": "pass\n",
                "rationale": "Attempt to bypass protected validation",
            }
        )
    plugin.config.proposal.write_text(json.dumps(proposal))
    reference = tmp_path / "reference.json"
    reference.write_text(
        json.dumps(
            {
                "metadata": {"model": "synthetic-demo"},
                "fields": {
                    "synthetic_mass": {
                        "units": "1",
                        "shape": [1],
                        "values": [4999950000.0],
                        "weights": [1.0],
                    }
                },
            }
        )
    )
    data = plugin.config.model_dump()
    data.update(
        workflow="debug",
        benchmark_identity={},
        debug={
            "reference_dataset": reference,
            "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            "expected_exit_code": 1,
            "failure_signature": "ATOM_EXPECTED_FAILURE",
            "protected_files": (("MAPL", "run.py"),),
        },
    )
    data["commands"] = {k: v for k, v in data["commands"].items() if k in {"build", "run"}}
    data["commands"]["reproduce"] = (
        sys.executable,
        "-c",
        "from kernel import compute; assert compute() == 4999950000.0, 'ATOM_EXPECTED_FAILURE'",
    )
    if case == "wrong-failure":
        data["commands"]["reproduce"] = (
            sys.executable,
            "-c",
            "raise RuntimeError('unrelated failure')",
        )
    if case == "changed-reference":
        reference.write_text(reference.read_text() + "\n")
    if case == "wrong-science":
        data["phase_commands"] = {
            "candidate": {
                "run": (
                    sys.executable,
                    "-c",
                    "import run,json; from pathlib import Path; p=Path('results/fields.json'); "
                    "d=json.loads(p.read_text()); d['fields']['synthetic_mass']['values'][0]+=1; p.write_text(json.dumps(d))",
                )
            }
        }
    return GEOSPlugin(GEOSConfig.model_validate(data))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "healthy",
        "wrong-failure",
        "bad-repair",
        "harness-edit",
        "changed-reference",
        "wrong-science",
    ],
)
async def test_debug_gates_require_reproduction_repair_and_reference(tmp_path, case):
    plugin = debug_plugin(tmp_path, case)
    registry = CapabilityRegistry()
    registry.register(plugin)
    goal = Goal(
        objective="Repair the specified synthetic bug", constraints=plugin.goal_constraints()
    )
    store = Store(tmp_path / "state")
    try:
        state = await Controller(
            registry, PluginPlanner(plugin), store, Budget(max_experiments=2, wall_seconds=90)
        ).run(goal)
        history = store.history(goal.id)
        assert len(history) == 1
        experiment = history[0]
        directory = store.directory(experiment.id)
        assert "geos.repair" in goal.constraints and "geos.performance" not in goal.constraints
        assert (state["status"] == "succeeded") == (case == "valid")
        if case == "valid":
            assert all(e.passed for e in experiment.evaluations)
            a = json.loads((directory / "evidence/baseline-reproduce.json").read_text())
            b = json.loads((directory / "evidence/candidate-reproduce.json").read_text())
            assert a["status"] == "failed" and a["reproduction_gate_passed"]
            assert b["status"] == "succeeded" and b["returncode"] == 0
            assert a["argv"] == b["argv"]
            assert "trusted reference" in (directory / "evidence/debug-reference.json").read_text()
        else:
            assert state["best_valid_candidate"] is None
        if case in {"healthy", "wrong-failure", "changed-reference", "harness-edit"}:
            assert not (directory / "evidence/proposal.json").exists()
        if case != "healthy":
            assert (tmp_path / "fixture/baseline/kernel.py").read_text().endswith("return -1.0\n")
        assert all(a.verify(directory) for a in experiment.artifacts)
    finally:
        store.close()


@pytest.mark.asyncio
async def test_debug_runtime_receives_failure_and_replans_after_bad_repair(tmp_path):
    plugin = debug_plugin(tmp_path)
    runtime = tmp_path / "runtime.py"
    runtime.write_text("""import hashlib,json,sys
r=json.load(sys.stdin)
e=r['evidence']
assert 'debug_diagnosis' in e and 'baseline_benchmark' not in e
assert 'ATOM_EXPECTED_FAILURE' in e['debug_diagnosis']['failure']['stderr']['text']
f=e['files'][0]
content='def compute():\\n    return 4999950000.0\\n' if e['previous_task_results'] else 'def compute():\\n    return -2.0\\n'
print(json.dumps({'proposal': {'summary':'Scripted repair','changes':[{'repository':f['repository'],'path':f['path'],'before_sha256':f['before_sha256'],'content':content,'rationale':'Scripted debug case'}]},'rationale':'Uses failure evidence'}))
""")
    data = plugin.config.model_dump()
    data.update(
        proposal=None, runtime_argv=(sys.executable, str(runtime)), targets=(("MAPL", "kernel.py"),)
    )
    plugin = GEOSPlugin(GEOSConfig.model_validate(data))
    registry = CapabilityRegistry()
    registry.register(plugin)
    goal = Goal(objective="Repair with feedback", constraints=plugin.goal_constraints())
    store = Store(tmp_path / "state")
    try:
        controller = Controller(
            registry, PluginPlanner(plugin), store, Budget(max_experiments=2, wall_seconds=90)
        )
        state = await controller.run(goal)
        assert state["status"] == "succeeded"
        history = store.history(goal.id)
        assert len(history) == 2 and history[0].status == "rejected"
        assert all(e.passed for e in history[1].evaluations)
        assert (await controller.run(goal))["usage"] == state["usage"]
    finally:
        store.close()


def test_debug_config_requires_fixed_reproducer_and_reference(tmp_path):
    plugin = debug_plugin(tmp_path)
    data = plugin.config.model_dump()
    with pytest.raises(ValueError, match="reference/failure policy"):
        GEOSConfig.model_validate({**data, "debug": None})
    with pytest.raises(ValueError, match="identical"):
        GEOSConfig.model_validate(
            {**data, "phase_commands": {"candidate": {"reproduce": ("true",)}}}
        )
    with pytest.raises(ValueError, match="exactly one"):
        GEOSConfig.model_validate({**data, "runtime_argv": ("model",)})
