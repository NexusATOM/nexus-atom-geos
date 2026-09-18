import json
import sys

import pytest
from nexus_atom_controller import Controller, Store
from nexus_atom_controller.discovery import PluginPlanner
from nexus_atom_core import Budget, CapabilityRegistry, Goal

from nexus_atom_geos.config import GEOSConfig
from nexus_atom_geos.plugin import GEOSPlugin


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["success", "citation", "budget", "omit", "mutate", "timeout", "omit-all"]
)
async def test_atom_specialists_are_scoped_budgeted_and_feed_proposals(tmp_path, case):
    plugin = GEOSPlugin.demo(tmp_path / "fixture")
    script = tmp_path / "runtime.py"
    calls = tmp_path / "calls.jsonl"
    script.write_text("""import json,sys
from pathlib import Path
r=json.load(sys.stdin); e=r['evidence']
with Path(sys.argv[1]).open('a') as f: f.write(json.dumps({'capability':r['task']['capability'],'evidence':e})+'\\n')
if r['task']['capability']=='geos.review_specialist':
    if sys.argv[2]=='timeout':
        import time
        time.sleep(20)
    assert r['capabilities']==[]
    assert len(e['contexts'])==1 and e['contexts'][0]['repository']=='MAPL'
    assert 'experiment:baseline-fields.json' in e['observations']
    assert 'policy:science' in e['observations']
    if e['profile']['name']=='second': assert sys.argv[3]=='alternate'
    ref='invented' if sys.argv[2]=='citation' else e['contexts'][0]['evidence'][0]['id']
    proposal={'summary':e['profile']['name'],'findings':[{'summary':'Review','evidence_ids':[ref]}]}
    if sys.argv[2]=='mutate' and e['profile']['name']=='first':
        import yaml
        profile=json.loads(Path('workspace.json').read_text())['profile']
        workspace=yaml.safe_load(Path(profile).read_text())
        kernel=Path(profile).parent/ workspace['repositories'][0]['path'] / 'kernel.py'
        kernel.write_text(kernel.read_text()+'# changed after review\\n')
    tokens=5
else:
    assert set(e['specialist_assessments'])=={'first','second'}
    assert e['specialist_assessments']['second']['summary']=='second'
    f=e['files'][0]
    proposal={'summary':'Synthetic optimization','changes':[{'repository':f['repository'],'path':f['path'],
      'before_sha256':f['before_sha256'],'content':'def compute():\\n    return 4999950000.0\\n','rationale':'Reviewed'}]}
    tokens=3
print(json.dumps({'proposal':proposal,'rationale':'test','runtime':'local','usage':{'tokens':tokens}}))
""")
    data = plugin.config.model_dump()
    data.update(
        proposal=None,
        runtime_argv=(sys.executable, str(script), str(calls), case, "default"),
        targets=(("MAPL", "kernel.py"),),
        warmups=0,
        objective_tags=("conservation",),
        specialists=(
            {
                "name": "first",
                "instructions": "Review conservation",
                "repositories": ["MAPL"],
                "objective_tags": ["conservation"],
            },
            {"name": "second", "instructions": "Review reproducibility", "repositories": ["MAPL"]},
            {"name": "inactive", "instructions": "Review CUDA", "objective_tags": ["gpu"]},
        ),
        specialist_runtimes={
            "first": {
                "runtime_argv": (sys.executable, str(script), str(calls), case, "default"),
                "timeout_seconds": 1 if case == "timeout" else 120,
            },
            "second": {
                "runtime_argv": (sys.executable, str(script), str(calls), case, "alternate")
            },
            "inactive": {"runtime_argv": ("must-not-run",)},
        },
    )
    plugin = GEOSPlugin(GEOSConfig.model_validate(data))
    registry = CapabilityRegistry()
    registry.register(plugin)
    goal = Goal(objective="Reviewed synthetic modernization", constraints=plugin.goal_constraints())
    store = Store(tmp_path / "state")
    budget = Budget(
        max_experiments=1,
        max_tokens=100,
        max_tasks=7 if case == "budget" else 100,
        wall_seconds=120,
    )
    try:
        planner = PluginPlanner(plugin)
        if case in {"omit", "omit-all"}:
            from nexus_atom_geos.workflows import modernization_plan

            class MissingReviewPlanner(PluginPlanner):
                async def plan(self, goal, history, registry):
                    if case == "omit-all":
                        from nexus_atom_geos.workflows import _sequential_plan

                        return _sequential_plan(
                            [
                                ("inspect", "baseline"),
                                ("build", "baseline"),
                                ("run", "baseline"),
                                ("benchmark", "baseline"),
                                ("build", "candidate"),
                                ("run", "candidate"),
                                ("benchmark", "candidate"),
                                ("validate", "candidate"),
                            ],
                            None,
                            "Bypass reviewers",
                        )
                    return modernization_plan()

            planner = MissingReviewPlanner(plugin)
        controller = Controller(registry, planner, store, budget)
        state = await controller.run(goal)
        history = store.history(goal.id)
        recorded = (
            [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
        )
        if case == "success":
            assert state["status"] == "succeeded"
            assert state["usage"]["tokens"] == 0
            assert len(recorded) == 3
            skipped = next(r for r in history[0].results if r.task_id == "specialist-inactive")
            assert skipped.outputs["selected"] is False
            assert (await controller.run(goal))["usage"] == state["usage"]
            policy = json.loads(
                (store.directory(history[0].id) / "evidence/site-policy.json").read_text()
            )
            assert (
                len(policy["specialists"]) == 3
                and policy["specialist_runtimes"]["second"]["runtime_argv"][-1] == "alternate"
            )
        else:
            assert state["best_valid_candidate"] is None
            assert state["usage"]["tokens"] == 0
            assert len(recorded) == (
                0 if case in {"omit", "omit-all"} else 2 if case == "mutate" else 1
            )
            assert all(r["capability"] == "geos.review_specialist" for r in recorded)
            if case == "timeout":
                assert any("TimeoutError" in (r.error or "") for r in history[0].results)
            if case == "mutate":
                assert any("review source changed" in (r.error or "") for r in history[0].results)
            if case == "omit-all":
                assert any(
                    e.evaluator.endswith("software") and not e.passed
                    for e in history[0].evaluations
                )
            if case == "omit":
                assert any("preparation task" in (r.error or "") for r in history[0].results)
            if case == "citation":
                assert any("unavailable evidence" in (r.error or "") for r in history[0].results)
        assert all(a.verify(store.directory(e.id)) for e in history for a in e.artifacts)
        if case == "budget":
            changed = plugin.config.model_dump()
            changed["specialists"][0]["instructions"] = "Changed reviewer policy"
            replacement = GEOSPlugin(GEOSConfig.model_validate(changed))
            changed_registry = CapabilityRegistry()
            changed_registry.register(replacement)
            await Controller(
                changed_registry,
                PluginPlanner(replacement),
                store,
                Budget(max_experiments=2, max_tasks=100, wall_seconds=120),
            ).run(goal)
            latest = store.history(goal.id)[-1]
            assert any("configuration differs" in (r.error or "") for r in latest.results)
            assert len(calls.read_text().splitlines()) == 1
    finally:
        store.close()


def test_specialist_configuration_rejects_ambiguous_routes(tmp_path):
    data = GEOSPlugin.demo(tmp_path / "fixture").config.model_dump()
    with pytest.raises(ValueError, match="proposal runtime"):
        GEOSConfig.model_validate(
            {**data, "specialists": ({"name": "a", "instructions": "Review"},)}
        )
    with pytest.raises(ValueError, match="unknown profile"):
        GEOSConfig.model_validate(
            {**data, "specialist_runtimes": {"missing": {"runtime_argv": ["model"]}}}
        )


@pytest.mark.asyncio
async def test_invalid_review_preserves_runtime_usage(tmp_path, monkeypatch):
    from nexus_atom_agents import AgentResult, NOOARuntime
    from nexus_atom_core import ExecutionContext, Task, TaskResult, Usage

    from geos_agents.registry import RepositoryRegistry
    from nexus_atom_geos import specialist_adapter

    class Agent:
        async def propose(self, request):
            assert "previous_task_results" not in request["task"]["parameters"]
            assert "OUT_OF_SCOPE" not in json.dumps(request)
            return AgentResult(
                runtime="nooa",
                rationale="test",
                usage=Usage(tokens=9, cost=0.1),
                proposal={
                    "summary": "Invalid",
                    "findings": [{"summary": "Unknown", "evidence_ids": ["invented"]}],
                },
            )

    monkeypatch.setattr(
        specialist_adapter, "NOOARuntime", lambda model: NOOARuntime(model, agent=Agent())
    )
    config = GEOSPlugin.demo(tmp_path / "fixture").config.model_dump()
    config.update(
        proposal=None,
        nooa_model="fake",
        targets=(("MAPL", "kernel.py"),),
        specialists=({"name": "reviewer", "instructions": "Review"},),
    )
    config = GEOSConfig.model_validate(config)
    directory = tmp_path / "experiment"
    (directory / "evidence").mkdir(parents=True)
    result, usage = await specialist_adapter.review(
        config,
        RepositoryRegistry.from_file(config.workspace),
        Task(
            id="review", capability="geos.review_specialist", parameters={"specialist": "reviewer"}
        ),
        ExecutionContext(
            goal=Goal(objective="Review"), experiment_id="experiment", directory=directory
        ),
    )
    assert isinstance(result, TaskResult) and result.status == "failed"
    assert result.usage.tokens == 9 and result.usage.cost == 0.1 and usage is None
