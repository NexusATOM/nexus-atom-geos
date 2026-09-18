"""Session administration and a small resumable terminal interface."""

import asyncio
import json
import sys
from pathlib import Path

import yaml

from geos_agents.engineering import EngineeringPolicy
from geos_agents.models import GEOSTask, PatchProposal, Workflow
from geos_agents.registry import RepositoryRegistry
from geos_agents.sessions import GEOSSession, SessionRequest, SessionStore
from geos_agents.specialists import add_specialist_arguments, task_specialists

DEFAULT_DB = Path(".geos-agent/sessions.sqlite3")


def register(commands):
    session = commands.add_parser("session", help="manage durable sessions and dependency graphs")
    actions = session.add_subparsers(dest="session_action", required=True)
    create = actions.add_parser("create")
    create.add_argument("--objective", required=True)
    create.add_argument("--workspace", type=Path, required=True)
    actions.add_parser("list")
    for name in ("show", "history", "verify", "recover", "refresh"):
        actions.add_parser(name).add_argument("session_id")
    add = actions.add_parser("add")
    add_specialist_arguments(add)
    add.add_argument("session_id")
    add.add_argument("task")
    add.add_argument(
        "--workflow", choices=[w.value for w in Workflow] + ["work"], default="investigate"
    )
    add.add_argument("--depends-on", action="append", default=[])
    add.add_argument("--parent")
    add.add_argument("--repo", action="append", default=[])
    add.add_argument("--constraint", action="append", default=[])
    add.add_argument("--file", action="append", default=[])
    add.add_argument("--policy", type=Path)
    mode = add.add_mutually_exclusive_group()
    mode.add_argument("--model")
    mode.add_argument("--proposal", type=Path)
    add.add_argument("--execute", action="store_true")
    run = actions.add_parser("run")
    run.add_argument("session_id")
    run.add_argument("--max-tasks", type=int, default=1)
    retry = actions.add_parser("retry")
    retry.add_argument("session_id")
    retry.add_argument("task_id")
    decide = actions.add_parser("decide")
    decide.add_argument("session_id")
    decide.add_argument("summary")
    promote = actions.add_parser("promote")
    promote.add_argument("session_id")
    promote.add_argument("finding_id")
    promote.add_argument("--scope", required=True)
    memory = actions.add_parser("memory")
    memory.add_argument("--scope", required=True)
    for subparser in actions.choices.values():
        subparser.add_argument("--db", type=Path, default=DEFAULT_DB)
    resume = commands.add_parser("resume", help="resume the latest or a named session")
    resume.add_argument("session_id", nargs="?")
    resume.add_argument("--db", type=Path, default=DEFAULT_DB)
    resume.add_argument("--status-only", action="store_true")


def _request(args) -> SessionRequest:
    targets = []
    for item in args.file:
        if ":" not in item:
            raise ValueError("--file must be REPOSITORY:relative/path")
        targets.append(tuple(item.split(":", 1)))
    kind = "work" if args.workflow == "work" else "workflow"
    policy = (
        EngineeringPolicy.model_validate(yaml.safe_load(args.policy.read_text()))
        if args.policy
        else None
    )
    proposal = (
        PatchProposal.model_validate_json(args.proposal.read_text()) if args.proposal else None
    )
    return SessionRequest(
        task=GEOSTask(
            description=args.task,
            **task_specialists(args),
            workflow=Workflow.IMPLEMENT if kind == "work" else Workflow(args.workflow),
            repositories=tuple(args.repo),
            constraints=tuple(args.constraint) or ("preserve scientific meaning",),
        ),
        kind=kind,
        model=args.model,
        targets=tuple(targets),
        policy=policy,
        proposal=proposal,
        execute=args.execute,
    )


def handle(args) -> int:
    with SessionStore(args.db) as store:
        if args.command == "resume":
            entries = store.list()
            session_id = args.session_id or (entries[0]["id"] if entries else None)
            if not session_id:
                raise ValueError(
                    "No saved sessions. Start with: geos-agent session create --workspace PROFILE --objective 'YOUR OBJECTIVE'"
                )
            if args.status_only or not sys.stdin.isatty():
                print(store.snapshot(session_id).model_dump_json(indent=2))
                return 0
            store.recover(session_id)
            return _repl(store, session_id)
        action = args.session_action
        result = None
        if action == "create":
            result = {
                "session_id": store.create(
                    args.objective, RepositoryRegistry.from_file(args.workspace)
                )
            }
        elif action == "list":
            result = store.list()
        elif action == "add":
            result = {
                "task_id": store.add(
                    args.session_id,
                    _request(args),
                    depends_on=tuple(args.depends_on),
                    parent=args.parent,
                )
            }
        elif action == "show":
            result = store.snapshot(args.session_id).model_dump(mode="json")
        elif action == "run":
            state = asyncio.run(
                GEOSSession(store, args.session_id).run_pending(max_tasks=args.max_tasks)
            )
            print(state.model_dump_json(indent=2))
            return 1 if any(t.status in {"failed", "interrupted"} for t in state.tasks) else 0
        elif action == "retry":
            store.retry(args.session_id, args.task_id)
            result = {"task_id": args.task_id, "status": "pending"}
        elif action == "recover":
            result = {"interrupted_tasks": store.recover(args.session_id)}
        elif action == "refresh":
            store.refresh(args.session_id)
            result = {"session_id": args.session_id, "workspace": "refreshed"}
        elif action == "history":
            result = store.history(args.session_id)
        elif action == "verify":
            result = store.verify(args.session_id)
            print(json.dumps({"passed": not result, "failures": result}, indent=2))
            return 1 if result else 0
        elif action == "decide":
            result = {"decision_id": store.decide(args.session_id, args.summary)}
        elif action == "promote":
            result = {"memory_id": store.promote(args.session_id, args.finding_id, args.scope)}
        elif action == "memory":
            result = store.memory(args.scope)
        print(json.dumps(result, indent=2))
        return 0


def _repl(store: SessionStore, session_id: str) -> int:
    print(f"GEOS session {session_id}: {store.snapshot(session_id).objective}")
    print("/status /history /agents /findings /run /retry TASK_ID /decision TEXT /refresh /exit")
    print(
        "Plain text queues an offline investigation. Use session add for model/engineering options."
    )
    while True:
        try:
            line = input("geos> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        try:
            if line in {"/exit", "/quit"}:
                return 0
            if line == "/status":
                print(store.snapshot(session_id).model_dump_json(indent=2))
            elif line == "/history":
                print(json.dumps(store.history(session_id), indent=2))
            elif line == "/agents":
                print(
                    json.dumps(
                        [
                            {"task": t.id, "agent": t.assigned_to, "status": t.status}
                            for t in store.snapshot(session_id).tasks
                        ],
                        indent=2,
                    )
                )
                print("Specialist delegation events are retained in each task's events.jsonl.")
            elif line == "/findings":
                print(json.dumps(store.snapshot(session_id).findings, indent=2))
            elif line == "/run":
                state = asyncio.run(GEOSSession(store, session_id).run_pending())
                print(json.dumps({t.id: t.status for t in state.tasks}, indent=2))
            elif line.startswith("/retry "):
                store.retry(session_id, line.split(maxsplit=1)[1])
            elif line.startswith("/decision "):
                store.decide(session_id, line.split(maxsplit=1)[1])
            elif line == "/refresh":
                store.refresh(session_id)
            elif line.startswith("/"):
                print(
                    "Unknown command. Use /status /history /agents /findings /run /retry /decision /refresh /exit."
                )
            else:
                print(
                    "Queued:",
                    store.add(session_id, SessionRequest(task=GEOSTask(description=line))),
                )
        except Exception as exc:
            detail = f": {exc}" if isinstance(exc, (ValueError, OSError)) else ""
            print(f"Session action failed ({type(exc).__name__}){detail}")
