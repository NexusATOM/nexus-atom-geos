"""Investigate → modify → build → validate → benchmark → report.

Only deterministic configured gates can award a validated status. A model's
opinion cannot turn a failed gate into success. Execution is opt-in and isolated.
"""

from __future__ import annotations

import asyncio
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from geos_agents.benchmark import BenchmarkEnvironment, benchmark, compare_benchmarks
from geos_agents.context import confined_file, digest, git_state
from geos_agents.models import Contract, GEOSTask, PatchProposal, TimingEvidence, Workflow
from geos_agents.patches import PatchManager
from geos_agents.registry import RepositoryRegistry
from geos_agents.trace import RunTrace
from geos_agents.validation import FieldDataset, TolerancePolicy, compare_fields
from geos_agents.workflows import WorkflowRunner
from geos_agents.workspace import GEOSWorkspace


class Gate(Contract):
    repository: str
    command: str
    kind: Literal["build", "validation"]


class NumericalGate(Contract):
    repository: str
    output: str
    policy: TolerancePolicy


class BenchmarkGate(Contract):
    repository: str
    command: str
    environment: BenchmarkEnvironment
    repeats: int = Field(default=5, ge=2, le=100)
    warmups: int = Field(default=1, ge=0, le=20)
    minimum_speedup: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class EngineeringPolicy(Contract):
    gates: tuple[Gate, ...] = Field(min_length=2)
    numerical: tuple[NumericalGate, ...] = Field(min_length=1)
    benchmarks: tuple[BenchmarkGate, ...] = Field(min_length=1)
    max_repairs: int = Field(default=0, ge=0, le=3)

    @model_validator(mode="after")
    def complete_ladder(self):
        if self.gates[0].kind != "build" or not any(g.kind == "validation" for g in self.gates):
            raise ValueError("Engineering gates must begin with a build and include validation")
        return self


class EngineeringRunner:
    def __init__(self, registry: RepositoryRegistry, output_root: Path):
        self.registry = registry
        self.output_root = output_root
        self.last_trace: RunTrace | None = None

    async def work(
        self,
        task: GEOSTask,
        policy: EngineeringPolicy,
        *,
        execute: bool = False,
        llm=None,
        proposal: PatchProposal | None = None,
        targets: tuple[tuple[str, str], ...] = (),
    ) -> dict:
        trace = RunTrace(self.output_root, kind="engineering")
        self.last_trace = trace
        report = {
            "run_id": trace.run_id,
            "task": task.model_dump(mode="json"),
            "status": "planned",
            "scientific_validation": "not_certified",
            "attempts": [],
            "limitations": [
                "Configured software/numerical gates are not full scientific certification.",
                "Worktree artifacts are retained for review; original checkouts are not patched.",
            ],
        }
        trace.artifact("task.json", task)
        trace.artifact("policy.json", policy)
        with self._reporting(trace, report), trace.span("engineering", execute=execute):
            self._preflight(policy)
            if not execute:
                report["next_step"] = (
                    "Review policy, then pass --execute with a model and targets or an existing proposal."
                )
                trace.artifact("report.json", report)
                return report
            if (llm is None) == (proposal is None):
                raise ValueError("Execution requires exactly one of a model or a prepared proposal")
            if llm is not None and not targets:
                raise ValueError("Model-driven work requires explicit file targets")
            if proposal is not None and not proposal.changes:
                raise ValueError("Prepared proposal has no changes")
            target_names = {self.registry.get(name).name for name, _ in targets}
            if proposal:
                target_names |= {
                    self.registry.get(change.repository).name for change in proposal.changes
                }
            selected = tuple(dict.fromkeys((*task.repositories, *sorted(target_names))))
            implementation_task = task.model_copy(
                update={"workflow": Workflow.IMPLEMENT, "repositories": selected}
            )
            self.registry.select(implementation_task)
            # Preserve the whole bound federation in isolation so build-relative paths keep working.
            workspace = GEOSWorkspace(self.registry, trace).isolate(trace.directory / "checkouts")
            report["workspace"] = str(trace.directory / "workspace.yaml")
            report["repositories"] = {
                b.name: {"path": str(b.path), "git": git_state(b.path).model_dump(mode="json")}
                for b in workspace.repositories.bindings.values()
            }
            baseline_ok, baseline_steps = self._gates(workspace, policy, "baseline")
            report["baseline_gates"] = baseline_steps
            if not baseline_ok:
                return self._finish(trace, report, "baseline_failed")
            baseline_data = self._datasets(workspace, policy, "baseline")
            baseline_benchmarks = self._benchmarks(workspace, policy, "baseline")
            report["baseline_benchmarks"] = [b.model_dump(mode="json") for b in baseline_benchmarks]
            for binding in workspace.repositories.bindings.values():
                if git_state(binding.path).dirty is not False:
                    raise ValueError(
                        "Baseline commands changed the checkout; build outputs must be ignored"
                    )
            reasoning = WorkflowRunner(
                workspace.repositories,
                trace.directory / "reasoning",
                targets=targets,
                measurements=tuple(
                    TimingEvidence(
                        id=f"measurement:baseline:{index}",
                        repository=gate.repository,
                        command=gate.command,
                        median_seconds=measured.median_seconds,
                        min_seconds=measured.min_seconds,
                        max_seconds=measured.max_seconds,
                        trials=len(measured.samples),
                        environment=measured.environment.model_dump(mode="json"),
                    )
                    for index, (gate, measured) in enumerate(
                        zip(policy.benchmarks, baseline_benchmarks, strict=True)
                    )
                ),
            )
            if llm is not None:
                from geos_agents.agents import GEOSAgent

                result = await GEOSAgent(reasoning, llm=llm).solve(implementation_task)
                proposal = result.proposal
            if proposal is None or not proposal.changes:
                return self._finish(trace, report, "no_changes_proposed")
            allowed_targets = {
                (workspace.repositories.get(c.repository).name, c.path) for c in proposal.changes
            }
            for attempt in range(policy.max_repairs + 1):
                patch_trace = RunTrace(trace.directory / "patches", kind="patch")
                PatchManager(workspace.repositories, patch_trace).review(
                    proposal, apply=True, require_clean=attempt == 0
                )
                trace.emit(
                    "engineering.patch_applied",
                    attempt=attempt,
                    patch_run=str(patch_trace.directory),
                )
                gates_ok, steps = self._gates(workspace, policy, f"candidate-{attempt}")
                attempt_report = {
                    "attempt": attempt,
                    "gates": steps,
                    "patch_run": str(patch_trace.directory),
                }
                comparisons = []
                if gates_ok:
                    candidate_data = self._datasets(workspace, policy, f"candidate-{attempt}")
                    for index, gate in enumerate(policy.numerical):
                        compared = compare_fields(
                            baseline_data[index], candidate_data[index], gate.policy
                        )
                        comparisons.append(compared.model_dump(mode="json"))
                    attempt_report["numerical"] = comparisons
                    gates_ok = all(c["passed"] for c in comparisons)
                report["attempts"].append(attempt_report)
                if gates_ok:
                    candidates = self._benchmarks(workspace, policy, f"candidate-{attempt}")
                    speedups = [
                        compare_benchmarks(a, b)
                        for a, b in zip(baseline_benchmarks, candidates, strict=True)
                    ]
                    attempt_report["benchmarks"] = [b.model_dump(mode="json") for b in candidates]
                    attempt_report["performance"] = speedups
                    meets_performance = all(
                        g.minimum_speedup is None or s["speedup"] >= g.minimum_speedup
                        for g, s in zip(policy.benchmarks, speedups, strict=True)
                    )
                    return self._finish(
                        trace, report, "validated" if meets_performance else "performance_failed"
                    )
                if llm is None or attempt == policy.max_repairs:
                    return self._finish(trace, report, "validation_failed")
                # Repair only the initially selected files, using their current complete contents.
                from geos_agents.agents import RepositoryAgent

                repair = WorkflowRunner(
                    workspace.repositories,
                    trace.directory / "reasoning",
                    targets=tuple(sorted(allowed_targets)),
                )
                files = repair._patch_inputs(tuple(workspace.repositories.bindings))
                import json

                feedback = json.dumps(attempt_report, ensure_ascii=False)[-5000:]
                repair_task = implementation_task.model_copy(
                    update={
                        "description": task.description[:2500]
                        + "\nRepair the failed deterministic gates. Evidence:\n"
                        + feedback
                    }
                )
                with trace.span("repair", attempt=attempt + 1):
                    proposal = await asyncio.wait_for(
                        RepositoryAgent(llm=llm).propose(repair_task, files), timeout=120
                    )
                    WorkflowRunner._check_proposal(proposal, files)
                if not proposal.changes:
                    return self._finish(trace, report, "validation_failed")
        return report

    def _preflight(self, policy: EngineeringPolicy) -> None:
        for gate in (*policy.gates, *policy.benchmarks):
            binding = self.registry.get(gate.repository)
            spec = binding.commands.get(gate.command)
            expected = (
                "benchmark"
                if isinstance(gate, BenchmarkGate)
                else ("build" if gate.kind == "build" else "test")
            )
            if spec is None or spec.purpose != expected:
                raise ValueError(
                    f"{binding.name}:{gate.command} must be configured with purpose: {expected}"
                )
        for gate in policy.numerical:
            binding = self.registry.get(gate.repository)
            confined_file(binding.path, gate.output)

    @staticmethod
    def _gates(workspace, policy, phase):
        steps = []
        with workspace.artifacts.span("gates", phase=phase):
            # Require fresh experiment output on EVERY pass. A zero exit code
            # must never allow stale baseline output to masquerade as validation.
            for gate in policy.numerical:
                binding = workspace.repositories.get(gate.repository)
                path = confined_file(binding.path, gate.output)
                ignored = subprocess.run(
                    ["git", "-C", str(binding.path), "check-ignore", "-q", "--", gate.output],
                    capture_output=True,
                    timeout=10,
                )
                if ignored.returncode != 0:
                    raise ValueError("Numerical outputs must be Git-ignored generated artifacts")
                if any(
                    path.is_relative_to(p)
                    for p in workspace.repositories.excluded_roots(gate.repository)
                ):
                    raise ValueError("Numerical output belongs to another bound repository")
                if path.exists():
                    if not path.is_file():
                        raise ValueError("Numerical output path must be a file")
                    path.unlink()
            for gate in policy.gates:
                method = workspace.build if gate.kind == "build" else workspace.validate
                result = method(gate.repository, gate.command, execute=True)
                steps.append(result.model_dump(mode="json"))
                if result.status != "passed":
                    return False, steps
        return True, steps

    @staticmethod
    def _datasets(workspace, policy, phase):
        datasets = []
        for index, gate in enumerate(policy.numerical):
            root = workspace.repositories.get(gate.repository).path
            path = confined_file(root, gate.output)
            raw = path.read_bytes()
            dataset = FieldDataset.model_validate_json(raw)
            workspace.artifacts.artifact(f"{phase}-fields-{index}.json", dataset)
            workspace.artifacts.emit(
                "numerical.input",
                phase=phase,
                repository=gate.repository,
                path=gate.output,
                sha256=digest(raw),
            )
            datasets.append(dataset)
        return datasets

    @staticmethod
    def _benchmarks(workspace, policy, phase):
        results = []
        with workspace.artifacts.span("benchmarks", phase=phase):
            for gate in policy.benchmarks:
                results.append(
                    benchmark(
                        workspace.commands,
                        gate.repository,
                        gate.command,
                        gate.environment,
                        repeats=gate.repeats,
                        warmups=gate.warmups,
                    )
                )
        return results

    @staticmethod
    def _finish(trace, report, status):
        report["status"] = status
        trace.artifact("report.json", report)
        lines = [
            f"# GEOS engineering report: {status}",
            "",
            report["task"]["description"],
            "",
            "Scientific validation: **not certified**.",
            "",
            f"Candidate workspace: `{report['workspace']}`",
            "",
            f"Candidate attempts: {len(report['attempts'])}",
            "",
            "See report.json for command results, numerical checks, timings, and patch artifact paths.",
        ]
        lines += [
            "",
            "## Baseline gates",
            "",
            "| Repository / command | Status | Seconds |",
            "| --- | --- | ---: |",
        ]
        for step in report.get("baseline_gates", []):
            lines.append(
                f"| {step['repository']} / {step['command']} | {step['status']} | {step['elapsed_seconds']:.4f} |"
            )
        for attempt in report["attempts"]:
            lines += [
                "",
                f"## Candidate attempt {attempt['attempt'] + 1}",
                "",
                f"Patch and backups: `{attempt['patch_run']}`",
                "",
                "| Repository / command | Status | Seconds |",
                "| --- | --- | ---: |",
            ]
            for step in attempt["gates"]:
                lines.append(
                    f"| {step['repository']} / {step['command']} | {step['status']} | {step['elapsed_seconds']:.4f} |"
                )
            for comparison in attempt.get("numerical", []):
                lines += [
                    "",
                    "| Field | Pass | Max absolute error | Failed elements |",
                    "| --- | --- | ---: | ---: |",
                ]
                for name, field in comparison["fields"].items():
                    lines.append(
                        f"| {name} | {field['passed']} | {field['max_absolute_error']:.6g} | {field['failed_count']} |"
                    )
            for comparison in attempt.get("performance", []):
                lines += [
                    "",
                    f"Baseline median: {comparison['reference_median_seconds']:.6f} s. "
                    f"Candidate median: {comparison['candidate_median_seconds']:.6f} s. "
                    f"Measured wall-time ratio: {comparison['speedup']:.3f}×.",
                ]
        lines += ["", "## Repository provenance", ""]
        for name, binding in report.get("repositories", {}).items():
            lines.append(
                f"- {name}: baseline `{binding['git']['commit']}`, candidate `{binding['path']}`"
            )
        (trace.directory / "report.md").write_text("\n".join(lines) + "\n")
        trace.emit("run.completed", status=status)
        return report

    @staticmethod
    @contextmanager
    def _reporting(trace, report):
        try:
            yield
        except BaseException as exc:
            report["status"] = "error"
            report["error_type"] = type(exc).__name__
            if not (trace.directory / "report.json").exists():
                trace.artifact("report.json", report)
            raise
