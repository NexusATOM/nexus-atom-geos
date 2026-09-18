import hashlib
import json
import sys

import pytest
from nexus_atom_controller import Controller, Store
from nexus_atom_controller.discovery import PluginPlanner
from nexus_atom_core import Budget, CapabilityRegistry, Goal

from nexus_atom_geos.plugin import GEOSPlugin, log_excerpt, proposal_feedback


def test_log_excerpt_keeps_bounded_head_and_tail(tmp_path):
    log = tmp_path / "log"
    assert not log_excerpt(log)["available"]
    log.write_bytes(b"HEAD" + b"x" * 20000 + b"TAIL")
    excerpt = log_excerpt(log)
    assert excerpt["truncated"]
    assert excerpt["text"].startswith("HEAD")
    assert excerpt["text"].endswith("TAIL")
    assert len(excerpt["text"]) < 8300
    assert excerpt["bytes"] == 20008


@pytest.mark.asyncio
async def test_profile_and_build_failure_reach_next_proposal(tmp_path):
    plugin = GEOSPlugin.demo(tmp_path / "demo")
    script = tmp_path / "agent.py"
    script.write_text("""import json,sys
request=json.load(sys.stdin)
evidence=request["evidence"]
profile=evidence["baseline_profile"]
assert profile["status"] == "succeeded"
assert "function calls" in profile["stdout"]["text"]
previous=evidence["previous_task_results"]
if previous:
    failed=[result for result in previous if result["status"] == "failed"]
    assert failed
    prior=next(r["outputs"]["proposal_feedback"] for r in previous if "proposal_feedback" in r["outputs"])
    assert not prior["truncated"]
    assert json.loads(prior["text"])["changes"][0]["content"].startswith("def compute(:")
    assert "SyntaxError" in failed[0]["outputs"]["stderr"]["text"]
    content="def compute():\\n    return float(99999 * 100000 // 2)\\n"
else:
    content="def compute(:\\n    return 0\\n"
source=evidence["files"][0]
proposal={"summary":"Repair the measured candidate", "changes":[{
    "repository":source["repository"], "path":source["path"],
    "before_sha256":source["before_sha256"], "content":content,
    "rationale":"Use profile and previous compiler feedback"}],
    "required_validation":["Configured checks"]}
print(json.dumps({"proposal":proposal,"rationale":"test evidence"}))
""")
    plugin.config = plugin.config.model_copy(
        update={
            "proposal": None,
            "runtime_argv": (sys.executable, str(script)),
            "targets": (("MAPL", "kernel.py"),),
        }
    )
    registry = CapabilityRegistry()
    registry.register(plugin)
    store = Store(tmp_path / "state")
    goal = Goal(
        objective="Optimize and repair from evidence", constraints=plugin.goal_constraints()
    )
    result = await Controller(
        registry, PluginPlanner(plugin), store, Budget(max_experiments=2, wall_seconds=120)
    ).run(goal)
    history = store.history(goal.id)
    assert result["status"] == "succeeded", [r.error for e in history for r in e.results]
    assert [e.status for e in history] == ["rejected", "valid"]
    profile = json.loads(
        (store.directory(history[0].id) / "evidence/baseline-profile.json").read_text()
    )
    assert "function calls" in profile["stdout"]["text"]
    failed = next(r for r in history[0].results if r.status == "failed")
    assert "SyntaxError" in failed.outputs["stderr"]["text"]
    assert "for i in range" in (tmp_path / "demo/baseline/kernel.py").read_text()
    proposed = next(r for r in history[0].results if "proposal_feedback" in r.outputs)
    record = proposed.outputs["proposal_feedback"]
    raw = (store.directory(history[0].id) / record["artifact"]).read_bytes()
    assert record["sha256"] == hashlib.sha256(raw).hexdigest()
    assert json.loads(record["text"]) == json.loads(raw)
    assert all(a.verify(store.directory(e.id)) for e in history for a in e.artifacts)
    store.close()


def test_large_proposal_feedback_is_bounded_and_identifies_complete_artifact(tmp_path):
    path = tmp_path / "proposal.json"
    raw = json.dumps({"changes": [{"content": "x" * 200000}]}).encode()
    path.write_bytes(raw)
    record = proposal_feedback(path)
    assert record["truncated"] and record["bytes"] == len(raw)
    assert len(record["text"].encode()) < 65700
    assert record["sha256"] == hashlib.sha256(raw).hexdigest()
    assert path.read_bytes() == raw
