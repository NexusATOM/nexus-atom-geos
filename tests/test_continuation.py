import hashlib
import json
import sys

import pytest
from nexus_atom_controller import Controller, Store
from nexus_atom_controller.discovery import PluginPlanner
from nexus_atom_core import Budget, CapabilityRegistry, Goal

from nexus_atom_geos.config import GEOSConfig
from nexus_atom_geos.plugin import GEOSPlugin


@pytest.mark.asyncio
@pytest.mark.parametrize("corrupt,specialists", [(False, False), (True, False), (False, True)])
async def test_resume_continues_best_valid_candidate_and_preserves_baseline(
    tmp_path, corrupt, specialists
):
    plugin = GEOSPlugin.demo(tmp_path / "fixture")
    original = (tmp_path / "fixture/baseline/kernel.py").read_bytes()
    runtime = tmp_path / "runtime.py"
    runtime.write_text("""import json,sys
r=json.load(sys.stdin)['evidence']
if 'profile' in r:
    source=r['contexts'][0]['evidence'][0]
    assert 'for i in range' in source['text'] or '# stage1' in source['text']
    if '# stage1' in source['text']: assert any(k.startswith('parent:') for k in r['observations'])
    print(json.dumps({'proposal':{'summary':'Review reconstructed source','findings':[{'summary':'Source reviewed','evidence_ids':[source['id']]}]},'rationale':'Scripted review'}))
    sys.exit(0)
f=r['files'][0]
if r['continuation']['parent_experiment']:
    assert '# stage1' in f['content'], 'Rejected candidate must not seed subsequent work'
    assert any(x['outputs'].get('samples')==[5,5,5] for x in r['parent_candidate_results'])
    failed=any(x['status']=='failed' for x in r['previous_task_results'])
    content='def compute():\\n    return 4999950000.0 # stage3\\n' if failed else 'def compute():\\n    return -1.0 # rejected\\n'
else:
    assert 'for i in range' in f['content']
    content='def compute():\\n    return 4999950000.0 # stage1\\n'
print(json.dumps({'proposal':{'summary':'Synthetic continuation','changes':[{
'repository':f['repository'],'path':f['path'],'before_sha256':f['before_sha256'],
'content':content,'rationale':'Controlled continuation test'}]},'rationale':'Synthetic'}))
""")
    data = plugin.config.model_dump()
    data.update(
        proposal=None,
        runtime_argv=(sys.executable, str(runtime)),
        targets=(("MAPL", "kernel.py"),),
        continuation="best_valid",
        specialists=({"name": "reviewer", "instructions": "Review reconstructed source"},)
        if specialists
        else (),
        warmups=0,
        benchmark_seconds_file="results/timing.json",
    )
    data["commands"]["benchmark"] = (
        sys.executable,
        "-c",
        "import json; from pathlib import Path; s=Path('kernel.py').read_text(); "
        "Path('results/timing.json').write_text(json.dumps({'seconds':1 if 'stage3' in s else 5 if 'stage1' in s else 10}))",
    )
    plugin = GEOSPlugin(GEOSConfig.model_validate(data))
    registry = CapabilityRegistry()
    registry.register(plugin)
    goal = Goal(
        objective="Synthetic accumulation",
        target={"speedup": 5},
        constraints=plugin.goal_constraints(),
    )
    store = Store(tmp_path / "state")
    first = await Controller(
        registry, PluginPlanner(plugin), store, Budget(max_experiments=1, wall_seconds=120)
    ).run(goal)
    assert first["status"] == "budget_exhausted"
    parent = store.history(goal.id)[0]
    assert parent.status == "valid"
    if corrupt:
        (store.directory(parent.id) / "evidence/cumulative-proposal.json").write_text("{}")
    store.close()
    store = Store(tmp_path / "state")
    try:
        if corrupt:
            with pytest.raises(ValueError, match="artifact corrupted"):
                await Controller(
                    registry,
                    PluginPlanner(plugin),
                    store,
                    Budget(max_experiments=3, wall_seconds=180),
                ).run(goal)
            assert (tmp_path / "fixture/baseline/kernel.py").read_bytes() == original
            return
        state = await Controller(
            registry, PluginPlanner(plugin), store, Budget(max_experiments=3, wall_seconds=180)
        ).run(goal)
        history = store.history(goal.id)
        assert state["status"] == "succeeded"
        assert [e.status for e in history] == ["valid", "rejected", "valid"]
        for e in history[1:]:
            directory = store.directory(e.id)
            lineage = json.loads((directory / "evidence/continuation.json").read_text())
            assert lineage["parent_experiment"] == parent.id
            baseline = json.loads((directory / "evidence/baseline-benchmark.json").read_text())
            assert baseline["samples"] == [10, 10, 10]
        final = store.directory(history[-1].id)
        cumulative = json.loads((final / "evidence/cumulative-proposal.json").read_text())
        incremental = json.loads((final / "evidence/proposal.json").read_text())
        assert cumulative["changes"][0]["before_sha256"] == hashlib.sha256(original).hexdigest()
        assert (
            incremental["changes"][0]["before_sha256"] != cumulative["changes"][0]["before_sha256"]
        )
        assert all(a.verify(store.directory(e.id)) for e in history for a in e.artifacts)
        assert (tmp_path / "fixture/baseline/kernel.py").read_bytes() == original
    finally:
        store.close()


def test_continuation_rejects_prepared_or_non_modernization_config(tmp_path):
    config = GEOSPlugin.demo(tmp_path / "fixture").config.model_dump()
    with pytest.raises(ValueError, match="proposal runtime"):
        GEOSConfig.model_validate({**config, "continuation": "best_valid"})
    with pytest.raises(ValueError, match="modernization"):
        GEOSConfig.model_validate(
            {
                **config,
                "workflow": "regression",
                "continuation": "best_valid",
                "proposal": None,
                "runtime_argv": ("model",),
            }
        )


def test_cumulative_proposal_keeps_original_hashes_and_untouched_files():
    from geos_agents.models import FileChange, PatchProposal
    from nexus_atom_geos.continuation import cumulative_proposal

    first = FileChange(
        repository="MAPL", path="a.py", before_sha256="a" * 64, content="first", rationale="first"
    )
    untouched = first.model_copy(update={"path": "b.py", "content": "retained"})
    seed = PatchProposal(summary="seed", changes=(first, untouched))
    edit = first.model_copy(update={"before_sha256": "b" * 64, "content": "second"})
    added = first.model_copy(update={"path": "c.py", "before_sha256": None})
    combined = cumulative_proposal(seed, PatchProposal(summary="next", changes=(edit, added)))
    assert [(c.path, c.before_sha256, c.content) for c in combined.changes] == [
        ("a.py", "a" * 64, "second"),
        ("b.py", "a" * 64, "retained"),
        ("c.py", None, "first"),
    ]


def test_continuation_refuses_changed_original_commit(tmp_path):
    from nexus_atom_core import Artifact, Evaluation, ExecutionContext, Experiment

    from nexus_atom_geos.continuation import seed_candidate

    goal = Goal(objective="Keep baseline fixed")
    parent_dir = tmp_path / "parent"
    current_dir = tmp_path / "current"
    for directory in (parent_dir, current_dir):
        (directory / "evidence").mkdir(parents=True)
    path = parent_dir / "evidence/source-commits.json"
    path.write_text(json.dumps({"MAPL": {"commit": "old"}}))
    (current_dir / "evidence/source-commits.json").write_text(
        json.dumps({"MAPL": {"commit": "new"}})
    )
    parent = Experiment(
        id="parent",
        goal=goal.id,
        hypothesis="previous",
        tasks=(),
        results=(),
        artifacts=(Artifact.capture(path, parent_dir),),
        status="valid",
        evaluations=(Evaluation(evaluator="software", passed=True),),
    )
    context = ExecutionContext(
        goal=goal, experiment_id="current", directory=current_dir, parent_experiment=parent
    )
    with pytest.raises(ValueError, match="Original source commits changed"):
        seed_candidate(context, None, current_dir / "evidence", ())
