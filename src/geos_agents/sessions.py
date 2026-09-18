"""Durable session blackboard: SQLite for state, files for evidence, Git for source.

Private NOOA conversations are intentionally not persisted or copied between
agents. Resume occurs at task boundaries. Interrupted tasks require an explicit
retry, which starts a fresh run and retains the interrupted attempt's artifacts.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from geos_agents.context import digest, git_state
from geos_agents.engineering import EngineeringPolicy, EngineeringRunner
from geos_agents.models import Contract, GEOSTask, PatchProposal
from geos_agents.registry import RepositoryRegistry
from geos_agents.workflows import WorkflowRunner


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SessionRequest(Contract):
    task: GEOSTask
    kind: Literal["workflow", "work"] = "workflow"
    model: str | None = None
    targets: tuple[tuple[str, str], ...] = ()
    policy: EngineeringPolicy | None = None
    proposal: PatchProposal | None = None
    execute: bool = False

    @model_validator(mode="after")
    def valid_mode(self):
        if self.kind == "workflow" and (
            self.policy is not None or self.proposal is not None or self.execute
        ):
            raise ValueError(
                "Policy, prepared proposal and execution authorization belong to work tasks"
            )
        if self.kind == "work":
            if self.policy is None:
                raise ValueError("Work tasks require a saved engineering policy")
            if self.execute and (self.model is None) == (self.proposal is None):
                raise ValueError("Executed work requires exactly one of model or proposal")
            if self.execute and self.model and not self.targets:
                raise ValueError("Model-driven work requires explicit targets")
        return self


class TaskNode(Contract):
    id: str
    parent: str | None
    depends_on: tuple[str, ...]
    assigned_to: str = "GEOSAgent"
    status: Literal["pending", "running", "completed", "failed", "interrupted"]
    request: SessionRequest
    attempt: int
    output_dir: str | None
    result: dict = Field(default_factory=dict)
    error_type: str | None


class SessionState(Contract):
    schema_version: int = 1
    id: str
    objective: str
    workspace: dict
    repositories: dict
    created_at: str
    updated_at: str
    tasks: tuple[TaskNode, ...]
    findings: tuple[dict, ...]
    decisions: tuple[dict, ...]
    artifacts: tuple[dict, ...]


class SessionStore:
    """Transactional persistence. One OS-locked worker may execute a session at a time."""

    def __init__(self, database: Path):
        self.database = database.resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.root = self.database.parent / "sessions"
        self.connection = sqlite3.connect(self.database, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.connection.close()
            raise ValueError(f"Unsupported session database schema: {version}")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, objective TEXT NOT NULL, workspace TEXT NOT NULL,
                repositories TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                parent TEXT REFERENCES tasks(id), request TEXT NOT NULL, status TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 0, output_dir TEXT, result TEXT NOT NULL DEFAULT '{}',
                error_type TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dependencies (
                task_id TEXT NOT NULL REFERENCES tasks(id), dependency_id TEXT NOT NULL REFERENCES tasks(id),
                PRIMARY KEY(task_id, dependency_id)
            );
            CREATE TABLE IF NOT EXISTS findings (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                task_id TEXT NOT NULL REFERENCES tasks(id), data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                task_id TEXT NOT NULL REFERENCES tasks(id), attempt INTEGER NOT NULL,
                path TEXT NOT NULL, sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                summary TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memory (
                id TEXT PRIMARY KEY, scope TEXT NOT NULL, finding_id TEXT NOT NULL UNIQUE,
                data TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id),
                task_id TEXT, event TEXT NOT NULL, data TEXT NOT NULL, timestamp TEXT NOT NULL
            );
            PRAGMA user_version=1;
        """)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _event(self, session_id: str, event: str, task_id: str | None = None, **data):
        now = _now()
        self.connection.execute(
            "INSERT INTO events(session_id, task_id, event, data, timestamp) VALUES (?, ?, ?, ?, ?)",
            (session_id, task_id, event, json.dumps(data), now),
        )
        self.connection.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))

    def create(self, objective: str, registry: RepositoryRegistry) -> str:
        if not objective.strip() or len(objective) > 8000:
            raise ValueError("Session objective must contain 1–8000 characters")
        session_id = uuid4().hex
        workspace = {
            "repositories": [b.model_dump(mode="json") for b in registry.bindings.values()]
        }
        now = _now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    objective,
                    json.dumps(workspace),
                    json.dumps(self.fingerprints(registry)),
                    now,
                    now,
                ),
            )
            self._event(session_id, "session.created")
        (self.root / session_id).mkdir(parents=True, exist_ok=False)
        self.export(session_id)
        return session_id

    @staticmethod
    def fingerprints(registry: RepositoryRegistry) -> dict:
        return {
            name: {
                "path": str(b.path),
                "exists": b.path.is_dir(),
                "git": git_state(b.path).model_dump(mode="json"),
            }
            for name, b in registry.bindings.items()
        }

    def list(self) -> list[dict]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT id, objective, created_at, updated_at FROM sessions ORDER BY updated_at DESC, id DESC"
            )
        ]

    def _session(self, session_id: str):
        row = self.connection.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown session: {session_id}")
        return row

    def _task(self, session_id: str, task_id: str):
        row = self.connection.execute(
            "SELECT * FROM tasks WHERE id=? AND session_id=?", (task_id, session_id)
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown task in this session: {task_id}")
        return row

    @contextmanager
    def worker(self, session_id: str):
        import fcntl

        self._session(session_id)
        directory = self.root / session_id
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "worker.lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("This session already has an active worker") from exc
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def registry(self, session_id: str) -> RepositoryRegistry:
        from geos_agents.models import RepositoryBinding

        saved = json.loads(self._session(session_id)["workspace"])
        return RepositoryRegistry(
            [RepositoryBinding.model_validate(b) for b in saved["repositories"]]
        )

    def add(
        self,
        session_id: str,
        request: SessionRequest,
        *,
        depends_on: tuple[str, ...] = (),
        parent: str | None = None,
    ) -> str:
        registry = self.registry(session_id)
        registry.select(request.task)
        if request.kind == "work" and request.policy is None:
            raise ValueError("Engineering tasks require a saved policy")
        if request.kind != "work" and request.execute:
            raise ValueError("Only engineering tasks use execute authorization")
        # Edges can only point to existing nodes in the same session. Because
        # this API never rewrites edges, cycles are impossible by construction.
        for reference in (*depends_on, *((parent,) if parent else ())):
            self._task(session_id, reference)
        task_id = uuid4().hex
        now = _now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO tasks(id, session_id, parent, request, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (task_id, session_id, parent, request.model_dump_json(), now, now),
            )
            self.connection.executemany(
                "INSERT INTO dependencies VALUES (?, ?)",
                [(task_id, dependency) for dependency in dict.fromkeys(depends_on)],
            )
            self._event(session_id, "task.added", task_id, depends_on=list(depends_on))
        self.export(session_id)
        return task_id

    def snapshot(self, session_id: str) -> SessionState:
        row = self._session(session_id)
        tasks = []
        for task in self.connection.execute(
            "SELECT * FROM tasks WHERE session_id=? ORDER BY created_at, id", (session_id,)
        ):
            dependencies = tuple(
                r[0]
                for r in self.connection.execute(
                    "SELECT dependency_id FROM dependencies WHERE task_id=? ORDER BY dependency_id",
                    (task["id"],),
                )
            )
            tasks.append(
                TaskNode(
                    id=task["id"],
                    parent=task["parent"],
                    depends_on=dependencies,
                    status=task["status"],
                    request=SessionRequest.model_validate_json(task["request"]),
                    attempt=task["attempt"],
                    output_dir=task["output_dir"],
                    result=json.loads(task["result"]),
                    error_type=task["error_type"],
                )
            )
        findings = tuple(
            {"id": r["id"], "task_id": r["task_id"], **json.loads(r["data"])}
            for r in self.connection.execute(
                "SELECT * FROM findings WHERE session_id=? ORDER BY rowid", (session_id,)
            )
        )
        return SessionState(
            id=row["id"],
            objective=row["objective"],
            workspace=json.loads(row["workspace"]),
            repositories=json.loads(row["repositories"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            tasks=tuple(tasks),
            findings=findings,
            decisions=tuple(
                dict(r)
                for r in self.connection.execute(
                    "SELECT id, summary, created_at FROM decisions WHERE session_id=? ORDER BY created_at",
                    (session_id,),
                )
            ),
            artifacts=tuple(
                dict(r)
                for r in self.connection.execute(
                    "SELECT id, task_id, attempt, path, sha256 FROM artifacts WHERE session_id=? ORDER BY rowid",
                    (session_id,),
                )
            ),
        )

    def export(self, session_id: str) -> Path:
        from geos_agents.patches import _replace

        target = self.root / session_id / "state.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        _replace(target, self.snapshot(session_id).model_dump_json(indent=2).encode())
        return target

    def ready(self, session_id: str) -> tuple[TaskNode, ...]:
        snapshot = self.snapshot(session_id)
        states = {task.id: task.status for task in snapshot.tasks}
        return tuple(
            task
            for task in snapshot.tasks
            if task.status == "pending"
            and all(states[dependency] == "completed" for dependency in task.depends_on)
        )

    def recover(self, session_id: str) -> tuple[str, ...]:
        """Mark abandoned workers interrupted; never replay possible side effects silently."""
        with self.worker(session_id), self.connection:
            recovered = self._recover_locked(session_id)
        self.export(session_id)
        return recovered

    def _recover_locked(self, session_id: str) -> tuple[str, ...]:
        ids = tuple(
            r[0]
            for r in self.connection.execute(
                "SELECT id FROM tasks WHERE session_id=? AND status='running'", (session_id,)
            )
        )
        for task_id in ids:
            self.connection.execute(
                "UPDATE tasks SET status='interrupted', error_type='AbandonedWorker', updated_at=? WHERE id=?",
                (_now(), task_id),
            )
            self._event(session_id, "task.interrupted", task_id)
        return ids

    def retry(self, session_id: str, task_id: str) -> None:
        with self.worker(session_id), self.connection:
            row = self._task(session_id, task_id)
            if row["status"] not in {"failed", "interrupted"}:
                raise ValueError("Only failed or interrupted tasks can be retried")
            self.connection.execute(
                "UPDATE tasks SET status='pending', error_type=NULL, updated_at=? WHERE id=?",
                (_now(), task_id),
            )
            self._event(session_id, "task.retried", task_id, previous_attempt=row["attempt"])
        self.export(session_id)

    def refresh(self, session_id: str) -> None:
        """Explicitly accept changed source fingerprints for future tasks."""
        with self.worker(session_id), self.connection:
            self.connection.execute(
                "UPDATE sessions SET repositories=? WHERE id=?",
                (json.dumps(self.fingerprints(self.registry(session_id))), session_id),
            )
            self._event(session_id, "workspace.refreshed")
        self.export(session_id)

    def decide(self, session_id: str, summary: str) -> str:
        self._session(session_id)
        if not summary.strip() or len(summary) > 8000:
            raise ValueError("Decision must contain 1–8000 characters")
        decision_id = uuid4().hex
        with self.connection:
            self.connection.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?)",
                (decision_id, session_id, summary, _now()),
            )
            self._event(session_id, "decision.recorded", decision_id=decision_id)
        self.export(session_id)
        return decision_id

    def promote(self, session_id: str, finding_id: str, scope: str) -> str:
        row = self.connection.execute(
            "SELECT data FROM findings WHERE id=? AND session_id=?", (finding_id, session_id)
        ).fetchone()
        if row is None or not scope.strip() or len(scope) > 128:
            raise ValueError("A finding in this session and a nonempty scope are required")
        existing = self.connection.execute(
            "SELECT id, scope FROM memory WHERE finding_id=?", (finding_id,)
        ).fetchone()
        if existing:
            if existing["scope"] != scope:
                raise ValueError("Finding is already promoted to a different scope")
            return existing["id"]
        memory_id = uuid4().hex
        with self.connection:
            self.connection.execute(
                "INSERT INTO memory VALUES (?, ?, ?, ?, ?)",
                (memory_id, scope, finding_id, row[0], _now()),
            )
            self._event(session_id, "memory.promoted", finding_id=finding_id, scope=scope)
        return memory_id

    def memory(self, scope: str) -> tuple[dict, ...]:
        return tuple(
            {
                "id": r["id"],
                "scope": r["scope"],
                "created_at": r["created_at"],
                **json.loads(r["data"]),
            }
            for r in self.connection.execute(
                "SELECT * FROM memory WHERE scope=? ORDER BY created_at", (scope,)
            )
        )

    def verify(self, session_id: str) -> tuple[dict, ...]:
        failures = []
        for artifact in self.snapshot(session_id).artifacts:
            path = Path(artifact["path"])
            if not path.is_file() or digest(path.read_bytes()) != artifact["sha256"]:
                failures.append(
                    {"artifact": artifact["id"], "path": str(path), "status": "missing_or_changed"}
                )
        return tuple(failures)

    def history(self, session_id: str) -> list[dict]:
        self._session(session_id)
        return [
            {**dict(row), "data": json.loads(row["data"])}
            for row in self.connection.execute(
                "SELECT sequence, task_id, event, data, timestamp FROM events WHERE session_id=? ORDER BY sequence",
                (session_id,),
            )
        ]


class GEOSSession:
    """Execute a durable dependency graph without sharing specialist chat histories."""

    def __init__(self, store: SessionStore, session_id: str):
        store._session(session_id)
        self.store = store
        self.id = session_id

    def context(self, request: SessionRequest) -> str:
        state = self.store.snapshot(self.id)
        names = set(self.store.registry(self.id).select(request.task))
        findings = [f for f in state.findings if f.get("repository") in names][-8:]
        memory = [entry for name in sorted(names) for entry in self.store.memory(name)][-8:]
        # Historical evidence is explicitly non-authoritative for the current source.
        return json.dumps(
            {
                "objective": state.objective[:2000],
                "decisions": [d["summary"][:500] for d in state.decisions[-5:]],
                "historical_findings": [
                    {
                        "summary": f.get("summary", "")[:500],
                        "repository": f.get("repository"),
                        "commit": f.get("commit"),
                    }
                    for f in [*findings, *memory]
                ],
                "rule": "Historical findings and memory must be reverified against current source. They are not current validation results.",
            }
        )

    async def run_pending(self, *, max_tasks: int = 1, llm_factory=None) -> SessionState:
        if not 1 <= max_tasks <= 100:
            raise ValueError("max_tasks must be 1–100")
        store = self.store
        with store.worker(self.id):
            with store.connection:
                store._recover_locked(self.id)
            store.export(self.id)
            registry = store.registry(self.id)
            if store.fingerprints(registry) != store.snapshot(self.id).repositories:
                raise ValueError(
                    "Workspace changed since the session snapshot; inspect it, then use session refresh"
                )
            for _ in range(max_tasks):
                ready = store.ready(self.id)
                if not ready:
                    break
                node = ready[0]
                output = store.root / self.id / "tasks" / node.id / f"attempt-{node.attempt + 1}"
                output.mkdir(parents=True, exist_ok=False)
                with store.connection:
                    store.connection.execute(
                        "UPDATE tasks SET status='running', attempt=attempt+1, output_dir=?, updated_at=? WHERE id=? AND status='pending'",
                        (str(output), _now(), node.id),
                    )
                    store._event(
                        self.id,
                        "task.started",
                        node.id,
                        attempt=node.attempt + 1,
                        output_dir=str(output),
                    )
                store.export(self.id)
                request = node.request
                runner = None
                artifacts_recorded = False
                try:
                    llm = None
                    if request.model and (request.kind != "work" or request.execute):
                        if llm_factory is None:
                            import os

                            os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
                            from nooa.unifiedllm.registry import get_llm_client

                            llm_factory = get_llm_client
                        llm = llm_factory(request.model)
                    if request.kind == "work":
                        runner = EngineeringRunner(
                            registry, output, session_context=self.context(request)
                        )
                        result = await runner.work(
                            request.task,
                            request.policy,
                            execute=request.execute,
                            llm=llm,
                            proposal=request.proposal,
                            targets=request.targets,
                        )
                        successful = result["status"] in {"validated", "planned"}
                    else:
                        runner = WorkflowRunner(
                            registry,
                            output,
                            targets=request.targets,
                            session_context=self.context(request),
                        )
                        if llm:
                            from geos_agents.agents import GEOSAgent

                            generated = await GEOSAgent(runner, llm=llm).solve(request.task)
                        else:
                            generated = await runner.execute(request.task)
                        result = generated.model_dump(mode="json")
                        successful = result["status"] != "needs_context"
                    if runner.last_trace:
                        self._artifacts(node, runner.last_trace.directory)
                        artifacts_recorded = True
                    self._complete(node, result, "completed" if successful else "failed")
                except BaseException as exc:
                    status = "failed" if isinstance(exc, Exception) else "interrupted"
                    self._complete(
                        node, {"error_type": type(exc).__name__}, status, type(exc).__name__
                    )
                    raise
                finally:
                    if (
                        not artifacts_recorded
                        and runner is not None
                        and runner.last_trace is not None
                    ):
                        self._artifacts(node, runner.last_trace.directory)
                    store.export(self.id)
                if not successful:
                    break
        return store.snapshot(self.id)

    def _complete(self, node: TaskNode, result: dict, status: str, error_type=None):
        summary = {
            key: result[key]
            for key in ("status", "run_id", "mode", "repositories", "scientific_validation")
            if key in result
        }
        with self.store.connection:
            self.store.connection.execute(
                "UPDATE tasks SET status=?, result=?, error_type=?, updated_at=? WHERE id=?",
                (status, json.dumps(summary), error_type, _now(), node.id),
            )
            self.store._event(
                self.id, f"task.{status}", node.id, result=summary, error_type=error_type
            )
            self._findings(node, result)

    def _findings(self, node, result):
        contexts = {c["repository"]: c for c in result.get("contexts", [])}
        for assessment in result.get("assessments", {}).values():
            for finding in assessment.get("findings", []):
                repository = finding["evidence_ids"][0].split(":", 1)[0]
                context = contexts.get(repository, {})
                data = {
                    **finding,
                    "repository": repository,
                    "commit": context.get("git", {}).get("commit"),
                    "run_id": result.get("run_id"),
                    "attempt": node.attempt + 1,
                }
                self.store.connection.execute(
                    "INSERT INTO findings VALUES (?, ?, ?, ?)",
                    (uuid4().hex, self.id, node.id, json.dumps(data)),
                )

    def _artifacts(self, node: TaskNode, directory: Path):
        import os

        with self.store.connection:
            for parent, dirs, files in os.walk(directory):
                dirs[:] = [
                    d for d in dirs if d != "checkouts" and not (Path(parent) / d).is_symlink()
                ]
                for filename in files:
                    path = Path(parent) / filename
                    if path.is_symlink() or path.suffix not in {
                        ".json",
                        ".jsonl",
                        ".md",
                        ".diff",
                        ".yaml",
                    }:
                        continue
                    self.store.connection.execute(
                        "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            uuid4().hex,
                            self.id,
                            node.id,
                            node.attempt + 1,
                            str(path.resolve()),
                            digest(path.read_bytes()),
                        ),
                    )
                    if filename == "result.json" and path.parent.parent.name == "reasoning":
                        from geos_agents.models import GEOSResult

                        self._findings(
                            node,
                            GEOSResult.model_validate_json(path.read_bytes()).model_dump(
                                mode="json"
                            ),
                        )
