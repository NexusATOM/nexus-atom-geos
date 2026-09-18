"""GEOS capabilities over preserved federation tooling, HPC and generic science."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from pathlib import Path
from uuid import uuid4

from nexus_atom_core import (
    Artifact,
    Capability,
    Evaluation,
    Evaluator,
    ModelPlugin,
    TaskResult,
    Usage,
)
from nexus_atom_hpc import JobSpec, LocalScheduler, SlurmScheduler
from nexus_atom_science import DatasetArtifact, compare_fields, load_dataset

from geos_agents.context import confined_file, git_state
from geos_agents.models import PatchProposal
from geos_agents.patches import PatchManager
from geos_agents.registry import RepositoryRegistry
from geos_agents.trace import RunTrace
from geos_agents.workspace import GEOSWorkspace

from .config import GEOSConfig


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def log_excerpt(path: Path, limit: int = 8192) -> dict:
    """Bound prompt material while retaining both initial context and final errors."""
    if limit < 2:
        raise ValueError("Log excerpt limit must be at least two bytes")
    if not path.exists():
        return {"text": "", "available": False, "truncated": False}
    with path.open("rb") as stream:
        size = stream.seek(0, 2)
        stream.seek(0)
        if size <= limit:
            content = stream.read(limit)
        else:
            head = stream.read(limit // 2)
            tail_size = limit - len(head)
            stream.seek(-tail_size, 2)
            content = head + b"\n[... log excerpt truncated ...]\n" + stream.read(tail_size)
    return {
        "text": content.decode(errors="replace"),
        "available": True,
        "truncated": size > limit,
        "bytes": size,
    }


class GEOSCapability(Capability):
    def __init__(self, plugin, operation):
        self.plugin, self.operation = plugin, operation
        self.name = f"geos.{operation}"
        self.description = f"GEOS {operation} with recorded evidence and site configuration"

    async def execute(self, task, context):
        return await self.plugin.execute(self.operation, task, context)


class GEOSEvaluator(Evaluator):
    def __init__(self, plugin, name):
        self.plugin, self.name = plugin, name

    async def evaluate(self, goal, results, directory):
        evidence = directory / "evidence"
        if self.name == "software":
            records = [
                json.loads((evidence / f"{phase}-{kind}.json").read_text())
                for phase in ("baseline", "candidate")
                for kind in ("build", "run")
            ]
            return Evaluation(
                evaluator=self.name,
                passed=all(r["status"] == "succeeded" for r in records),
                evidence=tuple(
                    f"evidence/{phase}-{kind}.json"
                    for phase in ("baseline", "candidate")
                    for kind in ("build", "run")
                ),
            )
        if self.name == "performance":
            a, b = [
                json.loads((evidence / f"{phase}-benchmark.json").read_text())
                for phase in ("baseline", "candidate")
            ]
            if a["identity"] != b["identity"]:
                raise ValueError("Benchmark environments differ")
            if min(*a["samples"], *b["samples"]) <= 0:
                raise ValueError("Positive measured timings required")
            speedup = statistics.median(a["samples"]) / statistics.median(b["samples"])
            return Evaluation(
                evaluator=self.name,
                passed=True,
                metrics={"speedup": speedup},
                evidence=("evidence/baseline-benchmark.json", "evidence/candidate-benchmark.json"),
            )
        a, b = [
            DatasetArtifact.model_validate_json((evidence / f"{phase}-fields.json").read_text())
            for phase in ("baseline", "candidate")
        ]
        if self.name == "numerical":
            compared = compare_fields(a, b, self.plugin.config.tolerance)
            return Evaluation(
                evaluator=self.name,
                passed=compared.passed,
                metrics={f"numerical.{k}": v.value for k, v in compared.metrics.items()},
                evidence=("evidence/baseline-fields.json", "evidence/candidate-fields.json"),
            )
        evaluated = self.plugin.config.science.evaluate(a, b)
        return evaluated.model_copy(
            update={
                "metrics": {f"science.{k}": v for k, v in evaluated.metrics.items()},
                "evidence": ("evidence/baseline-fields.json", "evidence/candidate-fields.json"),
            }
        )


class GEOSPlugin(ModelPlugin):
    name = "geos"

    def __init__(self, config: GEOSConfig | None = None):
        self.config = config
        self.scheduler = (
            SlurmScheduler() if config and config.backend == "slurm" else LocalScheduler()
        )

    def capabilities(self):
        return [
            GEOSCapability(self, op)
            for op in (
                "inspect",
                "build",
                "run",
                "profile",
                "benchmark",
                "validate",
                "optimize",
                "diagnose",
            )
        ]

    def evaluators(self):
        return [
            GEOSEvaluator(self, name)
            for name in ("software", "numerical", "science", "performance")
        ]

    def _workspace(self, context):
        profile = json.loads((context.directory / "workspace.json").read_text())["profile"]
        return RepositoryRegistry.from_file(Path(profile))

    async def _command(self, operation, phase, context, registry):
        config = self.config
        argv = config.phase_commands.get(phase, {}).get(operation, config.commands.get(operation))
        if not argv:
            raise ValueError(f"Configure an explicit {operation} command")
        root = registry.get(config.repository).path
        spec = JobSpec(
            argv=argv,
            cwd=root,
            output_directory=context.directory / "jobs" / f"{phase}-{operation}-{uuid4().hex[:8]}",
            resources=config.phase_resources.get(phase, config.resources),
            environment=config.environment,
        )
        requested_gpu = spec.resources.gpus * spec.resources.nodes * spec.resources.seconds
        if requested_gpu > context.remaining.max_gpu_seconds:
            raise ValueError("Job allocation exceeds remaining GPU budget")
        job, result = await self.scheduler.run(spec)
        return {
            "job": job.model_dump(mode="json"),
            "status": result.state,
            "elapsed_seconds": result.elapsed_seconds,
            "gpu_seconds": result.gpu_seconds,
            "returncode": result.returncode,
            "stdout": log_excerpt(job.stdout_path),
            "stderr": log_excerpt(job.stderr_path),
        }

    async def execute(self, operation, task, context):
        if self.config is None:
            raise ValueError("GEOS requires a site configuration; use --config or --demo")
        directory = context.directory
        evidence = directory / "evidence"
        evidence.mkdir(exist_ok=True)
        phase = task.parameters.get("phase", "candidate")
        if phase not in {"baseline", "candidate"}:
            raise ValueError("Invalid experiment phase")
        outputs = {}
        usage = Usage()
        if operation == "inspect":
            original = RepositoryRegistry.from_file(self.config.workspace)
            trace = RunTrace(directory / "workspace-traces", kind="isolation")
            workspace = GEOSWorkspace(original, trace).isolate(directory / "source")
            write_json(
                directory / "workspace.json", {"profile": str(trace.directory / "workspace.yaml")}
            )
            outputs = {
                name: git_state(binding.path).model_dump(mode="json")
                for name, binding in workspace.repositories.bindings.items()
            }
            write_json(evidence / "source-commits.json", outputs)
            write_json(evidence / "site-policy.json", self.config.model_dump(mode="json"))
        else:
            registry = self._workspace(context)
            root = registry.get(self.config.repository).path
            if operation in {"build", "run", "profile"}:
                if operation == "run":
                    output = confined_file(root, self.config.dataset)
                    if output.exists():
                        output.unlink()
                outputs = await self._command(operation, phase, context, registry)
                write_json(evidence / f"{phase}-{operation}.json", outputs)
                usage = Usage(gpu_seconds=outputs["gpu_seconds"])
                if outputs["status"] != "succeeded":
                    return TaskResult(
                        task_id=task.id,
                        status="failed",
                        outputs=outputs,
                        usage=usage,
                        error=f"{operation} failed",
                    )
                if operation == "run":
                    data = load_dataset(confined_file(root, self.config.dataset))
                    write_json(evidence / f"{phase}-fields.json", data.model_dump(mode="json"))
            elif operation == "benchmark":
                samples = []
                gpu_seconds = 0
                for index in range(self.config.warmups + self.config.repeats):
                    timing_file = (
                        confined_file(root, self.config.benchmark_seconds_file)
                        if self.config.benchmark_seconds_file
                        else None
                    )
                    if timing_file and timing_file.exists():
                        timing_file.unlink()
                    remaining = context.remaining.model_copy(
                        update={"max_gpu_seconds": context.remaining.max_gpu_seconds - gpu_seconds}
                    )
                    measured = await self._command(
                        "benchmark",
                        phase,
                        context.model_copy(update={"remaining": remaining}),
                        registry,
                    )
                    gpu_seconds += measured["gpu_seconds"]
                    if measured["status"] != "succeeded":
                        return TaskResult(
                            task_id=task.id,
                            status="failed",
                            outputs=measured,
                            usage=Usage(gpu_seconds=gpu_seconds),
                            error="Benchmark command failed",
                        )
                    seconds = measured["elapsed_seconds"]
                    if timing_file:
                        seconds = float(json.loads(timing_file.read_text())["seconds"])
                    if not math.isfinite(seconds) or seconds <= 0:
                        raise ValueError("Benchmark timing must be finite and positive")
                    if index >= self.config.warmups:
                        samples.append(seconds)
                outputs = {
                    "samples": samples,
                    "identity": self.config.benchmark_identity,
                    "measurement": "application timing"
                    if self.config.benchmark_seconds_file
                    else "local process elapsed time",
                }
                write_json(evidence / f"{phase}-benchmark.json", outputs)
                usage = Usage(gpu_seconds=gpu_seconds)
            elif operation == "optimize":
                proposal_path = task.parameters.get("proposal") or self.config.proposal
                if proposal_path:
                    proposal = PatchProposal.model_validate_json(Path(proposal_path).read_text())
                elif self.config.nooa_model or self.config.runtime_argv:
                    from nexus_atom_agents import AgentContext, LocalRuntime, NOOARuntime

                    files = []
                    for repository, path in self.config.targets:
                        resolved = confined_file(registry.get(repository).path, path)
                        content = resolved.read_text()
                        files.append(
                            {
                                "repository": repository,
                                "path": path,
                                "content": content,
                                "before_sha256": hashlib.sha256(content.encode()).hexdigest(),
                            }
                        )
                    if not files:
                        raise ValueError("Agent optimization requires explicit target files")
                    runtime = (
                        LocalRuntime(self.config.runtime_argv)
                        if self.config.runtime_argv
                        else NOOARuntime(self.config.nooa_model)
                    )
                    result = await runtime.execute(
                        task,
                        AgentContext(
                            objective=context.goal.objective,
                            directory=directory,
                            max_output_tokens=min(4096, context.remaining.max_tokens),
                            evidence={
                                "files": files,
                                "previous_evaluations": task.parameters.get("feedback", []),
                                "previous_task_results": task.parameters.get(
                                    "previous_task_results", []
                                ),
                                "baseline_profile": json.loads(
                                    (evidence / "baseline-profile.json").read_text()
                                ),
                                "baseline_benchmark": json.loads(
                                    (evidence / "baseline-benchmark.json").read_text()
                                ),
                                "proposal_schema": PatchProposal.model_json_schema(),
                            },
                        ),
                        self.capabilities(),
                    )
                    proposal = PatchProposal.model_validate(result.proposal)
                    allowed = {(f["repository"], f["path"]) for f in files}
                    if any((c.repository, c.path) not in allowed for c in proposal.changes):
                        raise ValueError("Agent changed an unauthorized target")
                    usage = result.usage
                else:
                    raise ValueError("Configure a prepared proposal or a runtime and target files")
                if not proposal.changes:
                    raise ValueError("Empty optimization proposal")
                trace = RunTrace(directory / "patches", kind="optimization")
                PatchManager(registry, trace).review(proposal, apply=True, require_clean=True)
                outputs = {"summary": proposal.summary, "changes": len(proposal.changes)}
                write_json(evidence / "proposal.json", proposal.model_dump(mode="json"))
                import subprocess

                for name, binding in registry.bindings.items():
                    diff = subprocess.run(
                        ["git", "-C", str(binding.path), "diff", "--binary"],
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=30,
                    ).stdout
                    (evidence / f"{name}.patch").write_text(diff)
            elif operation in {"validate", "diagnose"}:
                evaluations = []
                for name in ("numerical", "science"):
                    evaluations.append(
                        (
                            await GEOSEvaluator(self, name).evaluate(
                                context.goal, tuple(context.previous_results.values()), directory
                            )
                        ).model_dump(mode="json")
                    )
                outputs = {"evaluations": evaluations}
                write_json(evidence / f"{operation}.json", outputs)
                if not all(e["passed"] for e in evaluations):
                    return TaskResult(
                        task_id=task.id,
                        status="failed",
                        outputs=outputs,
                        error="Deterministic validation failed",
                    )
        file = evidence / f"task-{task.id}.json"
        write_json(file, outputs)
        return TaskResult(
            task_id=task.id,
            status="succeeded",
            outputs=outputs,
            usage=usage,
            artifacts=(Artifact.capture(file, directory),),
        )

    @classmethod
    def from_config(cls, path):
        return cls(GEOSConfig.from_file(path))

    @classmethod
    def demo(cls, directory):
        from .demo import prepare_demo

        return cls(prepare_demo(directory))

    def goal_constraints(self):
        return tuple(f"geos.{name}" for name in ("software", "numerical", "science", "performance"))

    async def plan(self, goal, history, registry):
        from .workflows import modernization_plan

        if history and self.config.proposal:
            return None
        feedback = ""
        if history:
            feedback = " Previous attempt: " + json.dumps(
                [e.model_dump(mode="json") for e in history[-1].evaluations]
            )
        plan = modernization_plan(hypothesis=goal.objective + feedback)
        tasks = tuple(
            task.model_copy(
                update={
                    "parameters": {
                        **task.parameters,
                        "feedback": [e.model_dump(mode="json") for e in history[-1].evaluations]
                        if history
                        else [],
                        "previous_task_results": [
                            r.model_dump(mode="json") for r in history[-1].results
                        ]
                        if history
                        else [],
                    }
                }
            )
            if task.capability == "geos.optimize"
            else task
            for task in plan.graph.tasks
        )
        return plan.model_copy(update={"graph": plan.graph.model_copy(update={"tasks": tasks})})
