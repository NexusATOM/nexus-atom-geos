"""Command-line interface. Offline inspection is the default; models are explicit."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import yaml

from geos_agents import __version__
from geos_agents.catalog import CATALOG
from geos_agents.context import ContextLoader
from geos_agents.models import GEOSTask, Workflow
from geos_agents.registry import RepositoryRegistry
from geos_agents.workflows import WorkflowRunner


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="geos-agent", description=__doc__)
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="show curated GEOS repository responsibilities")
    init = commands.add_parser("init", help="import existing GEOSgcm mepo components")
    init.add_argument("--mepo", type=Path, required=True, help="GEOSgcm fixture directory")
    init.add_argument("--output", type=Path, default=Path("workspace.yaml"))
    inspect = commands.add_parser("inspect", help="inspect one bound repository without an LLM")
    inspect.add_argument("repository")
    inspect.add_argument("--query", default="")
    inspect.add_argument("--workspace", type=Path, required=True)
    graph = commands.add_parser("graph", help="show curated relationships for bound repositories")
    graph.add_argument("--workspace", type=Path, required=True)
    for workflow in Workflow:
        cmd = commands.add_parser(workflow.value, help=f"run the {workflow.value} workflow")
        cmd.add_argument("task")
        cmd.add_argument("--workspace", type=Path, required=True)
        cmd.add_argument("--repo", action="append", default=[])
        cmd.add_argument("--constraint", action="append", default=[])
        cmd.add_argument("--max-repos", type=int, default=3)
        cmd.add_argument("--context-chars", type=int, default=24000)
        cmd.add_argument("--call-timeout", type=float, default=120)
        mode = cmd.add_mutually_exclusive_group()
        mode.add_argument(
            "--model", help="explicit NOOA/LiteLLM model name; enables live reasoning"
        )
        mode.add_argument("--offline", action="store_true", help="source inventory only (default)")
        cmd.add_argument("--output", type=Path, default=Path(".geos-agent/runs"))
        cmd.add_argument("--json", action="store_true")
        if workflow == Workflow.IMPLEMENT:
            cmd.add_argument(
                "--file",
                action="append",
                default=[],
                help="explicit REPOSITORY:relative/path to edit",
            )
    return root


async def _workflow(args) -> tuple[object, WorkflowRunner]:
    registry = RepositoryRegistry.from_file(args.workspace)
    targets = []
    for value in getattr(args, "file", []):
        if ":" not in value:
            raise ValueError("--file must be REPOSITORY:relative/path")
        name, path = value.split(":", 1)
        targets.append((name, path))
    runner = WorkflowRunner(
        registry,
        args.output,
        context_chars=args.context_chars,
        call_timeout=args.call_timeout,
        targets=tuple(targets),
    )
    task = GEOSTask(
        description=args.task,
        workflow=Workflow(args.command),
        repositories=tuple(args.repo),
        constraints=tuple(args.constraint) or ("preserve scientific meaning",),
        max_repositories=args.max_repos,
    )
    if args.model:
        # Prevent a LiteLLM price-table refresh from adding unrelated network I/O.
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
        from nooa.unifiedllm.registry import get_llm_client

        from geos_agents.agents import GEOSAgent

        agent = GEOSAgent(runner, llm=get_llm_client(args.model))
        result = await agent.solve(task)
    else:
        result = await runner.execute(task)
    return result, runner


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "catalog":
            print(json.dumps([s.model_dump(mode="json") for s in CATALOG], indent=2))
        elif args.command == "init":
            registry = RepositoryRegistry.from_mepo(args.mepo)
            registry.write(args.output)
            print(f"Wrote {len(registry.bindings)} repository bindings to {args.output}")
        elif args.command == "inspect":
            registry = RepositoryRegistry.from_file(args.workspace)
            print(
                ContextLoader(registry).load(args.repository, args.query).model_dump_json(indent=2)
            )
        elif args.command == "graph":
            registry = RepositoryRegistry.from_file(args.workspace)
            print(
                json.dumps(
                    {
                        "kind": "curated relationships, not compiler-derived dependencies",
                        "nodes": list(registry.bindings),
                        "edges": [
                            {"from": s.name, "to": related}
                            for s in CATALOG
                            if s.name in registry.bindings
                            for related in s.related
                            if related in registry.bindings
                        ],
                    },
                    indent=2,
                )
            )
        else:
            result, runner = asyncio.run(_workflow(args))
            if args.json:
                print(result.model_dump_json(indent=2))
            else:
                print(
                    f"{result.status} ({result.mode}): {', '.join(result.repositories) or 'no repositories'}"
                )
                print(f"Evidence and results: {runner.last_trace.directory}")
                print("Scientific validation: not run")
        return 0
    except (ValueError, OSError, yaml.YAMLError) as exc:
        print(f"geos-agent: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        # Provider exceptions can contain request credentials. Keep the CLI concise.
        print(
            f"geos-agent: workflow failed ({type(exc).__name__}); inspect events.jsonl in the output directory",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
