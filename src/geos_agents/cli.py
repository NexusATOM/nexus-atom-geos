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
from geos_agents.specialists import add_specialist_arguments, task_specialists
from geos_agents.workflows import WorkflowRunner


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="geos-agent", description=__doc__)
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    from geos_agents.session_cli import register

    register(commands)
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
    run = commands.add_parser("run", help="dry-run or execute a named workspace command")
    run.add_argument("repository")
    run.add_argument("name", help="command name from the workspace profile")
    run.add_argument("--workspace", type=Path, required=True)
    run.add_argument("--execute", action="store_true")
    run.add_argument("--output", type=Path, default=Path(".geos-agent/runs"))
    patch = commands.add_parser("patch", help="review or apply a guarded patch proposal")
    patch.add_argument("proposal", type=Path)
    patch.add_argument("--workspace", type=Path, required=True)
    patch.add_argument("--apply", action="store_true")
    patch.add_argument("--output", type=Path, default=Path(".geos-agent/runs"))
    compare = commands.add_parser("compare", help="compare JSON field datasets")
    compare.add_argument("reference", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--atol", type=float, default=0)
    compare.add_argument("--rtol", type=float, default=0)
    compare.add_argument("--bitwise", action="store_true")
    compare.add_argument("--conserve", action="append", default=[])
    compare.add_argument("--output", type=Path, default=Path(".geos-agent/runs"))
    bench = commands.add_parser("benchmark", help="measure a configured benchmark command")
    bench.add_argument("repository")
    bench.add_argument("name")
    bench.add_argument("--workspace", type=Path, required=True)
    bench.add_argument("--environment", type=Path, required=True)
    bench.add_argument("--repeats", type=int, default=5)
    bench.add_argument("--warmups", type=int, default=1)
    bench.add_argument("--execute", action="store_true")
    bench.add_argument("--output", type=Path, default=Path(".geos-agent/runs"))
    bench_compare = commands.add_parser(
        "benchmark-compare", help="compare compatible measured trials"
    )
    bench_compare.add_argument("reference", type=Path)
    bench_compare.add_argument("candidate", type=Path)
    work = commands.add_parser(
        "work", help="isolated investigate/edit/build/validate/benchmark workflow"
    )
    add_specialist_arguments(work)
    work.add_argument("task")
    work.add_argument("--workspace", type=Path, required=True)
    work.add_argument(
        "--policy", type=Path, required=True, help="explicit engineering gate policy YAML"
    )
    work.add_argument("--repo", action="append", default=[])
    work.add_argument("--constraint", action="append", default=[])
    work.add_argument("--file", action="append", default=[], help="REPOSITORY:relative/path")
    generation = work.add_mutually_exclusive_group()
    generation.add_argument("--model")
    generation.add_argument("--proposal", type=Path, help="use an existing proposal without an LLM")
    work.add_argument(
        "--execute", action="store_true", help="create worktrees and run configured gates"
    )
    work.add_argument("--output", type=Path, default=Path(".geos-agent/runs"))
    for workflow in Workflow:
        cmd = commands.add_parser(workflow.value, help=f"run the {workflow.value} workflow")
        add_specialist_arguments(cmd)
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
        **task_specialists(args),
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
    arguments = sys.argv[1:] if argv is None else argv
    args = parser().parse_args(arguments or ["resume"])
    try:
        if args.command in {"session", "resume"}:
            from geos_agents.session_cli import handle

            return handle(args)
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
        elif args.command == "work":
            result = asyncio.run(_engineering(args))
            print(json.dumps(result, indent=2))
            return 0 if result["status"] in {"planned", "validated"} else 1
        elif args.command in {"run", "patch", "compare", "benchmark", "benchmark-compare"}:
            return _tools(args)
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


async def _engineering(args) -> dict:
    from geos_agents.engineering import EngineeringPolicy, EngineeringRunner
    from geos_agents.models import PatchProposal

    registry = RepositoryRegistry.from_file(args.workspace)
    policy = EngineeringPolicy.model_validate(yaml.safe_load(args.policy.read_text()))
    proposal = (
        PatchProposal.model_validate_json(args.proposal.read_text()) if args.proposal else None
    )
    targets = []
    for value in args.file:
        if ":" not in value:
            raise ValueError("--file must be REPOSITORY:relative/path")
        targets.append(tuple(value.split(":", 1)))
    llm = None
    if args.model and args.execute:
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
        from nooa.unifiedllm.registry import get_llm_client

        llm = get_llm_client(args.model)
    task = GEOSTask(
        description=args.task,
        **task_specialists(args),
        workflow=Workflow.IMPLEMENT,
        repositories=tuple(args.repo),
        constraints=tuple(args.constraint) or ("preserve scientific meaning",),
    )
    runner = EngineeringRunner(registry, args.output)
    try:
        return await runner.work(
            task, policy, execute=args.execute, llm=llm, proposal=proposal, targets=tuple(targets)
        )
    finally:
        if runner.last_trace:
            print(f"Engineering artifacts: {runner.last_trace.directory}", file=sys.stderr)


def _tools(args) -> int:
    from geos_agents.benchmark import (
        BenchmarkEnvironment,
        BenchmarkResult,
        benchmark,
        compare_benchmarks,
    )
    from geos_agents.context import digest
    from geos_agents.execution import CommandRunner
    from geos_agents.models import PatchProposal
    from geos_agents.patches import PatchManager
    from geos_agents.trace import RunTrace
    from geos_agents.validation import FieldDataset, TolerancePolicy, compare_fields

    if args.command == "benchmark-compare":
        result = compare_benchmarks(
            BenchmarkResult.model_validate_json(args.reference.read_text()),
            BenchmarkResult.model_validate_json(args.candidate.read_text()),
        )
        print(json.dumps(result, indent=2))
        return 0
    trace = RunTrace(args.output, kind=args.command)
    print(f"Run artifacts: {trace.directory}", file=sys.stderr)
    with trace.span(args.command):
        if args.command == "compare":
            inputs = {}
            datasets = []
            for label, path in (("reference", args.reference), ("candidate", args.candidate)):
                raw = path.read_bytes()
                inputs[label] = {"path": str(path.resolve()), "sha256": digest(raw)}
                datasets.append(FieldDataset.model_validate_json(raw))
            trace.artifact("inputs.json", inputs)
            result = compare_fields(
                *datasets,
                TolerancePolicy(
                    atol=args.atol,
                    rtol=args.rtol,
                    bitwise=args.bitwise,
                    conserved_fields=tuple(args.conserve),
                ),
            )
            trace.artifact("comparison.json", result)
            code = 0 if result.passed else 1
        else:
            registry = RepositoryRegistry.from_file(args.workspace)
            if args.command == "patch":
                proposal = PatchProposal.model_validate_json(args.proposal.read_text())
                result = PatchManager(registry, trace).review(proposal, apply=args.apply)
                trace.artifact("result.json", result)
                code = 0
            else:
                runner = CommandRunner(registry, trace)
                if args.command == "benchmark" and args.execute:
                    environment = BenchmarkEnvironment.model_validate_json(
                        args.environment.read_text()
                    )
                    result = benchmark(
                        runner,
                        args.repository,
                        args.name,
                        environment,
                        repeats=args.repeats,
                        warmups=args.warmups,
                    )
                    trace.artifact("benchmark.json", result)
                    code = 0
                else:
                    result = runner.run(args.repository, args.name, execute=args.execute)
                    trace.artifact("command.json", result)
                    code = 0 if result.status in {"passed", "dry_run"} else 1
        print(
            result.model_dump_json(indent=2)
            if hasattr(result, "model_dump_json")
            else json.dumps(result, indent=2)
        )
        trace.emit("run.completed", exit_code=code)
        return code


if __name__ == "__main__":
    raise SystemExit(main())
