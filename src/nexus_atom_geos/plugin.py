"""GEOS capabilities over preserved federation tooling, HPC and generic science."""

from __future__ import annotations

import csv
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


def proposal_feedback(path: Path) -> dict:
    """Bound model context while identifying the complete sealed proposal artifact."""
    excerpt = log_excerpt(path, limit=65536)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        **excerpt,
        "sha256": digest,
        "artifact": "evidence/proposal.json",
        "source_policy": "Replacement proposal against the original configured source; no implicit accumulation",
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
        debug = self.plugin.config.workflow == "debug"
        if self.name == "repair":
            from .debugging import repair_verified

            return Evaluation(
                evaluator=self.name,
                passed=debug and repair_verified(evidence, self.plugin.config.debug),
                evidence=(
                    "evidence/baseline-reproduce.json",
                    "evidence/candidate-reproduce.json",
                    "evidence/debug-reference.json",
                    "evidence/debug-protected.json",
                    "evidence/proposal.json",
                ),
            )
        if self.name in {"software", "tests", "sanitizers"}:
            checks = self.plugin.config.software_checks
            kinds = (
                ("build", "run", *checks)
                if self.name == "software"
                else ("test" if self.name == "tests" else "sanitize",)
            )
            phases = ("candidate",) if debug else ("baseline", "candidate")
            records = [
                json.loads((evidence / f"{phase}-{kind}.json").read_text())
                for phase in phases
                for kind in kinds
            ]
            passed = all(r["status"] == "succeeded" for r in records)
            if self.name == "software" and self.plugin.config.specialists:
                by_id = {r.task_id: r for r in results}
                passed = passed and all(
                    (review := by_id.get(f"specialist-{profile.name}")) is not None
                    and review.status == "succeeded"
                    and review.outputs.get("profile") == profile.model_dump(mode="json")
                    and isinstance(review.outputs.get("selected"), bool)
                    and (not review.outputs["selected"] or "assessment" in review.outputs)
                    for profile in self.plugin.config.specialists
                )
            if debug and self.name == "software":
                from .debugging import repair_verified

                passed = passed and repair_verified(evidence, self.plugin.config.debug)
            return Evaluation(
                evaluator=self.name,
                passed=passed,
                evidence=tuple(
                    f"evidence/{phase}-{kind}.json" for phase in phases for kind in kinds
                ),
            )
        if self.name == "performance":
            a, b = [
                json.loads((evidence / f"{phase}-benchmark.json").read_text())
                for phase in ("baseline", "candidate")
            ]
            if not a["identity"] or a["identity"] != b["identity"]:
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
        if config and config.plot_fields:
            from importlib.util import find_spec

            if find_spec("matplotlib") is None:
                raise ValueError("Configured plot_fields require nexus-atom-geos[plots]")
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
                "test",
                "sanitize",
                "run",
                "profile",
                "benchmark",
                "validate",
                "optimize",
                "repair",
                "prepare_candidate",
                "review_specialist",
                "reproduce",
                "diagnose",
            )
        ]

    def evaluators(self):
        return [
            GEOSEvaluator(self, name)
            for name in (
                "software",
                "tests",
                "sanitizers",
                "numerical",
                "science",
                "performance",
                "repair",
            )
        ]

    def _workspace(self, context):
        profile = json.loads((context.directory / "workspace.json").read_text())["profile"]
        return RepositoryRegistry.from_file(Path(profile))

    async def _command(self, operation, phase, context, registry):
        config = self.config
        argv = config.phase_commands.get(phase, {}).get(operation, config.commands.get(operation))
        if not argv and operation == "profile" and phase == "candidate":
            argv = config.phase_commands.get("baseline", {}).get("profile")
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
            "argv": list(spec.argv),
            "status": result.state,
            "elapsed_seconds": result.elapsed_seconds,
            "gpu_seconds": result.gpu_seconds,
            "returncode": result.returncode,
            "stdout": log_excerpt(job.stdout_path),
            "stderr": log_excerpt(job.stderr_path),
        }

    def _prepare_candidate(self, context, registry, evidence):
        from .continuation import seed_candidate

        seed = None
        if self.config.continuation == "best_valid":
            seed = seed_candidate(context, registry, evidence, self.config.targets)
        lineage = {
            "policy": self.config.continuation,
            "parent_experiment": context.parent_experiment.id if seed else None,
            "baseline": (
                "trusted reference dataset"
                if self.config.workflow == "debug"
                else "original configured source, remeasured in this attempt"
            ),
        }
        write_json(evidence / "continuation.json", lineage)
        artifact = None
        if seed:
            path = evidence / "seed-proposal.json"
            write_json(path, seed.model_dump(mode="json"))
            artifact = Artifact.capture(path, context.directory).model_dump(mode="json")
        return {"lineage": lineage, "seed_artifact": artifact}

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
            from .specialist_adapter import verify_saved_configuration

            verify_saved_configuration(self.config, context)
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
            if self.config.workflow == "debug":
                from .debugging import prepare_debug

                prepare_debug(self.config, workspace.repositories, evidence)
        else:
            registry = self._workspace(context)
            root = registry.get(self.config.repository).path
            if operation == "prepare_candidate":
                if not self.config.specialists:
                    raise ValueError("Candidate preparation tasks require configured specialists")
                outputs = self._prepare_candidate(context, registry, evidence)
            elif operation == "review_specialist":
                from .specialist_adapter import require_preparation, review

                require_preparation(context)
                outputs, used = await review(self.config, registry, task, context)
                if isinstance(outputs, TaskResult):
                    return outputs
                if used is not None:
                    usage = used
            elif operation == "reproduce":
                if self.config.workflow != "debug":
                    raise ValueError("Reproduction requires workflow: debug")
                from .debugging import contains_signature, protection, reproduction_matches

                expected = json.loads((evidence / "debug-protected.json").read_text())
                if protection(registry, self.config.debug) != expected:
                    raise ValueError("Protected debug harness files changed")
                outputs = await self._command("reproduce", phase, context, registry)
                outputs["protected_unchanged"] = protection(registry, self.config.debug) == expected
                stream = Path(outputs["job"][f"{self.config.debug.signature_stream}_path"])
                outputs["signature_matched"] = stream.is_file() and contains_signature(
                    stream, self.config.debug.failure_signature
                )
                passed = (
                    reproduction_matches(outputs, self.config.debug)
                    if phase == "baseline"
                    else (
                        outputs["status"] == "succeeded"
                        and outputs["returncode"] == 0
                        and outputs["protected_unchanged"]
                    )
                )
                outputs["reproduction_gate_passed"] = passed
                write_json(evidence / f"{phase}-reproduce.json", outputs)
                usage = Usage(gpu_seconds=outputs["gpu_seconds"])
                if not passed:
                    return TaskResult(
                        task_id=task.id,
                        status="failed",
                        outputs=outputs,
                        usage=usage,
                        error="Configured debug reproduction gate failed",
                    )
            elif operation == "diagnose" and self.config.workflow == "debug":
                failure = json.loads((evidence / "baseline-reproduce.json").read_text())
                outputs = {
                    "kind": "recorded failure evidence; root cause not established",
                    "failure": failure,
                    "reference": json.loads((evidence / "debug-reference.json").read_text()),
                    "protected_files": json.loads((evidence / "debug-protected.json").read_text()),
                }
                write_json(evidence / "diagnosis.json", outputs)
            elif operation in {"build", "run", "profile", "test", "sanitize"}:
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
                if not self.config.benchmark_identity:
                    raise ValueError("Benchmarking requires an explicit environment identity")
                if self.config.backend == "slurm" and not self.config.benchmark_seconds_file:
                    raise ValueError("Slurm benchmarking requires application timing")
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
                timing_csv = evidence / f"{phase}-timings.csv"
                with timing_csv.open("x", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(("phase", "trial", "seconds", "measurement"))
                    for trial, seconds in enumerate(samples, start=1):
                        writer.writerow((phase, trial, seconds, outputs["measurement"]))
                outputs["timing_csv"] = str(timing_csv.relative_to(directory))
                usage = Usage(gpu_seconds=gpu_seconds)
            elif operation in {"optimize", "repair"}:
                if operation == "repair" and self.config.workflow != "debug":
                    raise ValueError("Repair requires workflow: debug")
                from .continuation import cumulative_proposal
                from .specialist_adapter import assessments, require_preparation

                prepared = (
                    require_preparation(context)
                    if self.config.specialists
                    else self._prepare_candidate(context, registry, evidence)
                )
                seed = None
                if prepared["seed_artifact"]:
                    artifact = Artifact.model_validate(prepared["seed_artifact"])
                    if not artifact.verify(directory):
                        raise ValueError("Prepared candidate artifact changed")
                    seed = PatchProposal.model_validate_json(
                        (directory / artifact.path).read_text()
                    )
                lineage = prepared["lineage"]
                reviews = (
                    assessments(self.config, context, registry) if self.config.specialists else {}
                )
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
                    observations = (
                        {"debug_diagnosis": json.loads((evidence / "diagnosis.json").read_text())}
                        if self.config.workflow == "debug"
                        else {
                            "baseline_profile": json.loads(
                                (evidence / "baseline-profile.json").read_text()
                            ),
                            "baseline_benchmark": json.loads(
                                (evidence / "baseline-benchmark.json").read_text()
                            ),
                        }
                    )
                    result = await runtime.execute(
                        task,
                        AgentContext(
                            objective=context.goal.objective,
                            directory=directory,
                            max_output_tokens=min(4096, context.remaining.max_tokens),
                            evidence={
                                "files": files,
                                "continuation": lineage,
                                "specialist_assessments": reviews,
                                "parent_candidate_results": [
                                    r.model_dump(mode="json")
                                    for r in context.parent_experiment.results
                                    if r.task_id
                                    in {
                                        t.id
                                        for t in context.parent_experiment.tasks
                                        if t.parameters.get("phase") == "candidate"
                                        and t.capability
                                        in {"geos.profile", "geos.benchmark", "geos.validate"}
                                    }
                                ]
                                if seed
                                else [],
                                "previous_evaluations": task.parameters.get("feedback", []),
                                "previous_task_results": task.parameters.get(
                                    "previous_task_results", []
                                ),
                                **observations,
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
                if self.config.workflow == "debug":
                    protected = {
                        (registry.get(repo).name, path)
                        for repo, path in self.config.debug.protected_files
                    }
                    if any(
                        (registry.get(change.repository).name, change.path) in protected
                        for change in proposal.changes
                    ):
                        raise ValueError("Repair cannot modify protected debug harness files")
                proposal = proposal.model_copy(
                    update={
                        "changes": tuple(
                            change.model_copy(
                                update={
                                    "repository": registry.get(change.repository).name,
                                    "path": Path(change.path).as_posix(),
                                }
                            )
                            for change in proposal.changes
                        )
                    }
                )
                combined = cumulative_proposal(seed, proposal)
                trace = RunTrace(directory / "patches", kind=operation)
                PatchManager(registry, trace).review(proposal, apply=True, require_clean=True)
                outputs = {"summary": proposal.summary, "changes": len(proposal.changes)}
                write_json(evidence / "proposal.json", proposal.model_dump(mode="json"))
                write_json(evidence / "cumulative-proposal.json", combined.model_dump(mode="json"))
                outputs["continuation"] = lineage
                outputs["proposal_feedback"] = proposal_feedback(evidence / "proposal.json")
                if seed:
                    outputs["proposal_feedback"]["source_policy"] = (
                        "Incremental proposal against the reconstructed parent candidate"
                    )
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
                if operation == "validate" and self.config.plot_fields:
                    from nexus_atom_science import generate_comparison

                    baseline, candidate = [
                        DatasetArtifact.model_validate_json(
                            (evidence / f"{name}-fields.json").read_text()
                        )
                        for name in ("baseline", "candidate")
                    ]
                    plots = evidence / "plots"
                    plots.mkdir(exist_ok=False)
                    outputs["plots"] = {}
                    for index, name in enumerate(self.config.plot_fields):
                        path = plots / f"field-{index:04d}.png"
                        generate_comparison(
                            baseline.fields[name], candidate.fields[name], path, title=name
                        )
                        outputs["plots"][name] = Artifact.capture(
                            path, directory, kind="plot"
                        ).model_dump(mode="json")
                    write_json(evidence / "plots.json", outputs["plots"])
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
        checks = self.config.software_checks if self.config else ()
        additional = tuple("tests" if check == "test" else "sanitizers" for check in checks)
        performance = (
            () if self.config and self.config.workflow != "modernization" else ("performance",)
        )
        repair = ("repair",) if self.config and self.config.workflow == "debug" else ()
        return tuple(
            f"geos.{name}"
            for name in ("software", *additional, "numerical", "science", *performance, *repair)
        )

    async def plan(self, goal, history, registry):
        from .workflows import debug_plan, modernization_plan, regression_plan

        if self.config.workflow == "regression":
            if "speedup" in goal.target:
                raise ValueError("Regression does not measure speedup; select modernization")
            if history:
                return None
            return regression_plan(
                proposal=str(self.config.proposal) if self.config.proposal else None,
                software_checks=self.config.software_checks,
                hypothesis=goal.objective,
            )
        if self.config.workflow == "debug" and "speedup" in goal.target:
            raise ValueError("Debugging does not measure speedup; select modernization")
        if history and self.config.proposal:
            return None
        feedback = ""
        if history:
            feedback = " Previous attempt: " + json.dumps(
                [e.model_dump(mode="json") for e in history[-1].evaluations]
            )
        planner = debug_plan if self.config.workflow == "debug" else modernization_plan
        plan = planner(
            hypothesis=goal.objective + feedback, software_checks=self.config.software_checks
        )
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
            if task.capability in {"geos.optimize", "geos.repair"}
            else task
            for task in plan.graph.tasks
        )
        plan = plan.model_copy(update={"graph": plan.graph.model_copy(update={"tasks": tasks})})
        if self.config.specialists:
            from .specialist_adapter import add_review_tasks

            plan = add_review_tasks(plan, self.config)
        return plan
