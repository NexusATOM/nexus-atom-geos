import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from geos_agents.engineering import EngineeringPolicy
from geos_agents.models import GEOSTask, PatchProposal, RepositoryBinding
from geos_agents.registry import RepositoryRegistry
from geos_agents.sessions import GEOSSession, SessionRequest, SessionStore


@pytest.fixture
def session_fixture(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "README.md").write_text("MAPL fields use explicit unit conventions.\n")
    registry = RepositoryRegistry([RepositoryBinding(name="MAPL", path=root)])
    return tmp_path / "sessions.sqlite3", registry


def request(description="Inspect MAPL fields"):
    return SessionRequest(task=GEOSTask(description=description, repositories=("MAPL",)))


async def test_session_resumes_completed_tasks_without_replaying_them(session_fixture):
    database, registry = session_fixture
    with SessionStore(database) as store:
        sid = store.create("Understand MAPL fields", registry)
        first = store.add(sid, request())
        second = store.add(
            sid, request("Explain the field interface"), depends_on=(first,), parent=first
        )
        assert [n.id for n in store.ready(sid)] == [first]
        state = await GEOSSession(store, sid).run_pending()
        assert [t.status for t in state.tasks] == ["completed", "pending"]
        assert state.findings and state.artifacts
        store.decide(sid, "Preserve all unit conventions")
    with SessionStore(database) as store:
        state = await GEOSSession(store, sid).run_pending(max_tasks=10)
        assert [t.status for t in state.tasks] == ["completed", "completed"]
        assert [t.attempt for t in state.tasks] == [1, 1]
        assert state.tasks[1].parent == first
        assert state.tasks[1].depends_on == (first,)
        assert state.tasks[1].id == second
        assert not store.verify(sid)
        assert json.loads((store.root / sid / "state.json").read_text()) == state.model_dump(
            mode="json"
        )
        assert "Preserve all unit conventions" in GEOSSession(store, sid).context(request())


async def test_artifact_tampering_and_explicit_scoped_memory(session_fixture):
    database, registry = session_fixture
    with SessionStore(database) as store:
        sid = store.create("Collect knowledge", registry)
        store.add(sid, request())
        state = await GEOSSession(store, sid).run_pending()
        finding = state.findings[0]
        memory_id = store.promote(sid, finding["id"], "MAPL")
        assert store.promote(sid, finding["id"], "MAPL") == memory_id
        assert store.memory("MAPL")[0]["id"] == memory_id
        assert store.memory("CUDA") == ()
        another = store.create("Use historical knowledge", registry)
        assert "reverified" in GEOSSession(store, another).context(request())
        assert finding["summary"] in GEOSSession(store, another).context(request())
        path = Path(state.artifacts[0]["path"])
        path.write_text(path.read_text() + "\n")
        assert store.verify(sid)[0]["status"] == "missing_or_changed"


async def test_failed_dependency_blocks_children_until_explicit_retry(session_fixture):
    database, registry = session_fixture
    root = registry.get("MAPL").path
    (root / "README.md").unlink()
    with SessionStore(database) as store:
        sid = store.create("Recover a missing context", registry)
        first = store.add(sid, request())
        store.add(sid, request(), depends_on=(first,))
        state = await GEOSSession(store, sid).run_pending(max_tasks=10)
        assert [t.status for t in state.tasks] == ["failed", "pending"]
        assert not store.ready(sid)
        old_output = state.tasks[0].output_dir
        (root / "README.md").write_text("MAPL fields\n")
        store.retry(sid, first)
        state = await GEOSSession(store, sid).run_pending(max_tasks=10)
        assert [t.status for t in state.tasks] == ["completed", "completed"]
        assert state.tasks[0].attempt == 2
        assert state.tasks[0].output_dir != old_output
        assert Path(old_output).exists()


def test_recovery_and_active_worker_exclusion(session_fixture):
    database, registry = session_fixture
    with SessionStore(database) as store:
        sid = store.create("Recover crash", registry)
        tid = store.add(sid, request())
        with store.worker(sid):
            with pytest.raises(ValueError, match="active worker"):
                store.recover(sid)
        with store.connection:
            store.connection.execute(
                "UPDATE tasks SET status='running', attempt=1 WHERE id=?", (tid,)
            )
        assert store.recover(sid) == (tid,)
        assert store.snapshot(sid).tasks[0].status == "interrupted"
        assert not store.ready(sid)
        store.retry(sid, tid)
        assert store.ready(sid)[0].attempt == 1
        with pytest.raises(ValueError, match="Only failed"):
            store.retry(sid, tid)


def test_graph_rejects_cross_session_and_unknown_dependencies(session_fixture):
    database, registry = session_fixture
    with SessionStore(database) as store:
        a, b = store.create("A", registry), store.create("B", registry)
        node = store.add(a, request())
        with pytest.raises(ValueError, match="Unknown task"):
            store.add(b, request(), depends_on=(node,))
        with pytest.raises(ValueError, match="Unknown task"):
            store.add(a, request(), depends_on=("future-task",))
        with pytest.raises(ValueError, match="Unknown session"):
            store.snapshot("../../outside")


async def test_source_changes_require_explicit_refresh(session_fixture):
    database, registry = session_fixture
    root = registry.get("MAPL").path
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ],
        check=True,
    )
    with SessionStore(database) as store:
        sid = store.create("Track source revisions", registry)
        store.add(sid, request())
        (root / "README.md").write_text("Changed MAPL context\n")
        with pytest.raises(ValueError, match="Workspace changed"):
            await GEOSSession(store, sid).run_pending()
        assert store.snapshot(sid).tasks[0].status == "pending"
        store.refresh(sid)
        assert (await GEOSSession(store, sid).run_pending()).tasks[0].status == "completed"


async def test_session_worker_passes_typed_history_to_real_nooa(session_fixture, monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    from nooa.unifiedllm import FakeLLMClient

    prompts = []

    class RecordingFake(FakeLLMClient):
        async def acall(self, *args, **kwargs):
            response = await super().acall(*args, **kwargs)
            prompts.append(json.dumps(self.last_messages))
            return response

    database, registry = session_fixture
    with SessionStore(database) as store:
        sid = store.create("Preserve MAPL field units", registry)
        store.decide(sid, "Do not change field units")
        store.add(sid, request().model_copy(update={"model": "scripted-model"}))
        llm = RecordingFake.with_code_responses(
            [json.dumps({"summary": "Review complete", "findings": []})] * 3
        )
        state = await GEOSSession(store, sid).run_pending(llm_factory=lambda _: llm)
        assert state.tasks[0].status == "completed"
        assert llm.call_count == 3
        assert "Do not change field units" in prompts[0]


async def test_session_executes_engineering_and_persists_candidate(session_fixture, tmp_path):
    database, _ = session_fixture
    demo = tmp_path / "demo"
    script = Path(__file__).resolve().parents[2] / "examples/legacy/run_engineering_demo.py"
    subprocess.run(
        [sys.executable, str(script), "--output", str(demo)], check=True, capture_output=True
    )
    registry = RepositoryRegistry.from_file(demo / "workspace.yaml")
    policy = EngineeringPolicy.model_validate(yaml.safe_load((demo / "policy.yaml").read_text()))
    proposal = PatchProposal.model_validate_json((demo / "proposal.json").read_text())
    with SessionStore(database) as store:
        sid = store.create("Optimize synthetic kernel", registry)
        store.add(
            sid,
            SessionRequest(
                task=GEOSTask(description="Synthetic exact-value optimization"),
                kind="work",
                policy=policy,
                proposal=proposal,
                execute=True,
            ),
        )
        state = await GEOSSession(store, sid).run_pending()
        assert state.tasks[0].status == "completed"
        assert state.tasks[0].result["status"] == "validated"
        assert any(a["path"].endswith("report.md") for a in state.artifacts)
        assert not store.verify(sid)


def test_session_cli_and_noninteractive_resume(session_fixture, capsys):
    from geos_agents.cli import main

    database, registry = session_fixture
    profile = database.parent / "workspace.yaml"
    registry.write(profile)
    db = ["--db", str(database)]
    assert (
        main(["session", "create", "--objective", "Session demo", "--workspace", str(profile), *db])
        == 0
    )
    sid = json.loads(capsys.readouterr().out)["session_id"]
    assert main(["session", "add", sid, "Inspect MAPL", *db]) == 0
    tid = json.loads(capsys.readouterr().out)["task_id"]
    assert main(["session", "run", sid, *db]) == 0
    assert json.loads(capsys.readouterr().out)["tasks"][0]["id"] == tid
    assert main(["resume", sid, "--status-only", *db]) == 0
    assert json.loads(capsys.readouterr().out)["tasks"][0]["status"] == "completed"
    assert main(["session", "verify", sid, *db]) == 0
    assert json.loads(capsys.readouterr().out)["passed"]


def test_interactive_session_queues_and_runs_offline_work(session_fixture, monkeypatch, capsys):
    from geos_agents.session_cli import _repl

    database, registry = session_fixture
    commands = iter(
        [
            "/status",
            "/history",
            "/agents",
            "/findings",
            "Inspect MAPL fields",
            "/run",
            "/decision Preserve units",
            "/refresh",
            "/unknown",
            "/retry missing",
            "/exit",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(commands))
    with SessionStore(database) as store:
        sid = store.create("Interactive demo", registry)
        assert _repl(store, sid) == 0
        state = store.snapshot(sid)
        assert state.tasks[0].status == "completed"
        assert state.decisions[0]["summary"] == "Preserve units"
        assert "Unknown command" in capsys.readouterr().out
