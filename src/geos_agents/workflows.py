"""Deterministic orchestration around selective NOOA reasoning."""

from __future__ import annotations

import asyncio
import json
import re
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

from geos_agents import __version__
from geos_agents.context import ContextLoader, confined_file
from geos_agents.models import (
    Assessment,
    Finding,
    GEOSResult,
    GEOSTask,
    PatchProposal,
    RepositoryContext,
    TimingEvidence,
    ValidationPlan,
    Workflow,
)
from geos_agents.registry import RepositoryRegistry
from geos_agents.trace import RunTrace

if TYPE_CHECKING:
    from nooa.unifiedllm import UnifiedLLM


def validation_plan(task: GEOSTask) -> ValidationPlan:
    checks = (
        "Build with the recorded compiler/MPI/CMake environment",
        "Run configured unit and regression tests",
        "Compare CPU oracle and candidate outputs using an explicit tolerance policy",
        "Check restart reproducibility with the same MPI decomposition",
    )
    if task.workflow == Workflow.GPU_PORT:
        checks += (
            "Run GPU memory/race sanitizers and check halo boundaries",
            "Compare bitwise output if exact numerics is a task constraint",
        )
    return ValidationPlan(
        software_checks=checks,
        scientific_checks=(
            "Check mass and energy conservation against an approved baseline",
            "Compare dynamics/physics tendencies and their units",
            "Review drift and stability in a longer integration",
        ),
        limitations=(
            "Plan only: no GEOS experiment or scientific validation has run.",
            "Site commands, input data, baseline commits and acceptable tolerances are required.",
            "Resolution labels do not imply configured runnable cases.",
        ),
    )


def check_citations(
    assessment: Assessment, contexts: tuple[RepositoryContext, ...], extra_ids: tuple[str, ...] = ()
) -> Assessment:
    known = {e.id for context in contexts for e in context.evidence} | set(extra_ids)
    unknown = {
        ref for finding in assessment.findings for ref in finding.evidence_ids if ref not in known
    }
    if unknown:
        raise ValueError(f"Agent cited unavailable evidence: {', '.join(sorted(unknown))}")
    return assessment


class WorkflowRunner:
    def __init__(
        self,
        registry: RepositoryRegistry,
        output_root: Path,
        *,
        context_chars: int = 24000,
        call_timeout: float = 120,
        targets: tuple[tuple[str, str], ...] = (),
        measurements: tuple[TimingEvidence, ...] = (),
    ):
        if not 0 < call_timeout <= 3600:
            raise ValueError("call_timeout must be in (0, 3600]")
        self.registry = registry
        self.output_root = output_root
        self.loader = ContextLoader(registry, max_chars=context_chars)
        self.call_timeout = call_timeout
        self.targets = targets
        self.measurements = measurements
        self.last_trace: RunTrace | None = None

    async def execute(self, task: GEOSTask, *, llm: UnifiedLLM | None = None) -> GEOSResult:
        trace = RunTrace(self.output_root)
        self.last_trace = trace
        with trace.span(
            "workflow", workflow=task.workflow.value, mode="nooa" if llm else "offline"
        ):
            trace.artifact("task.json", task)
            if self.measurements:
                trace.artifact(
                    "measurements.json", [m.model_dump(mode="json") for m in self.measurements]
                )
            trace.emit(
                "runtime.configured",
                package_version=__version__,
                nooa_version=version("nooa") if llm else None,
                model=getattr(llm, "model", None),
                call_timeout=self.call_timeout,
            )
            names = self.registry.select(task)
            patch_inputs = (
                self._patch_inputs(names)
                if task.workflow == Workflow.IMPLEMENT and self.targets
                else None
            )
            if llm and task.workflow == Workflow.IMPLEMENT and not patch_inputs:
                raise ValueError("implementation requires explicit --file REPOSITORY:path targets")
            trace.emit(
                "repositories.selected",
                repositories=list(names),
                max_repositories=task.max_repositories,
            )
            contexts = []
            for name in names:
                with trace.span("context", repository=name):
                    context = self.loader.load(name, task.description)
                    contexts.append(context)
                    trace.emit(
                        "context.loaded",
                        repository=name,
                        commit=context.git.commit,
                        evidence_ids=[e.id for e in context.evidence],
                        truncated=context.truncated,
                        scanned_files=context.scanned_files,
                    )
            contexts = tuple(contexts)
            trace.artifact("contexts.json", [c.model_dump(mode="json") for c in contexts])
            plan = validation_plan(task)
            assessments: dict[str, Assessment] = {}
            proposal = None
            usable = tuple(c for c in contexts if c.evidence)

            async def invoke(label, method, *args, citation_contexts=contexts, extra_ids=()):
                with trace.span("delegation", specialist=label):
                    report = await asyncio.wait_for(method(*args), timeout=self.call_timeout)
                    if isinstance(report, Assessment):
                        check_citations(report, citation_contexts, extra_ids)
                    trace.emit(
                        "delegation.result", specialist=label, result=report.model_dump(mode="json")
                    )
                    return report

            if llm and usable:
                from geos_agents.agents import (
                    ArchitectureAgent,
                    CUDAAgent,
                    PerformanceAgent,
                    RepositoryAgent,
                    ValidationAgent,
                )

                for context in usable:
                    # A fresh agent per repository prevents cross-repository conversation leakage.
                    assessments[context.repository] = await invoke(
                        f"RepositoryAgent:{context.repository}",
                        RepositoryAgent(llm=llm).investigate,
                        task,
                        context,
                        citation_contexts=(context,),
                    )
                measurement_ids = tuple(m.id for m in self.measurements)
                if self.measurements:
                    assessments["performance"] = await invoke(
                        "PerformanceAgent:diagnose",
                        PerformanceAgent(llm=llm).diagnose,
                        task,
                        self.measurements,
                        citation_contexts=(),
                        extra_ids=measurement_ids,
                    )
                assessments["architecture"] = await invoke(
                    "ArchitectureAgent",
                    ArchitectureAgent(llm=llm).synthesize,
                    task,
                    contexts,
                    dict(assessments),
                    self.measurements,
                    extra_ids=measurement_ids,
                )
                if task.workflow == Workflow.GPU_PORT or (
                    task.workflow == Workflow.IMPLEMENT
                    and re.search(r"\b(gpu|cuda)\b", task.description, re.IGNORECASE)
                ):
                    assessments["cuda"] = await invoke(
                        "CUDAAgent", CUDAAgent(llm=llm).plan, task, contexts
                    )
                    if not self.measurements:
                        assessments["performance"] = await invoke(
                            "PerformanceAgent", PerformanceAgent(llm=llm).plan, task, contexts
                        )
                assessments["validation"] = await invoke(
                    "ValidationAgent", ValidationAgent(llm=llm).review, task, contexts, plan
                )
                if task.workflow == Workflow.IMPLEMENT:
                    files = patch_inputs
                    proposal = await invoke(
                        "RepositoryAgent:propose",
                        RepositoryAgent(llm=llm).propose,
                        task,
                        files,
                        json.dumps(
                            {
                                "assessments": {
                                    name: {
                                        "summary": a.summary[:2000],
                                        "next_steps": [step[:500] for step in a.next_steps[:5]],
                                        "unknowns": [item[:500] for item in a.unknowns[:5]],
                                    }
                                    for name, a in assessments.items()
                                },
                                "measurements": [
                                    m.model_dump(mode="json") for m in self.measurements
                                ],
                            }
                        ),
                    )
                    self._check_proposal(proposal, files)
                    trace.artifact("proposal.json", proposal)
            else:
                for context in contexts:
                    assessments[context.repository] = Assessment(
                        summary=f"Offline evidence inventory for {context.repository}; no LLM reasoning performed.",
                        findings=tuple(
                            Finding(
                                summary=f"Source excerpt at {e.path}:{e.start_line}",
                                evidence_ids=(e.id,),
                                confidence="observed",
                            )
                            for e in context.evidence
                        ),
                        unknowns=context.notices,
                        next_steps=(
                            "Inspect the cited source or run with an explicitly configured model.",
                        ),
                    )
            status = "investigated"
            if task.workflow in (Workflow.GPU_PORT, Workflow.IMPLEMENT):
                status = "proposed" if proposal and proposal.changes else "planned"
            if len(usable) != len(contexts) or not usable:
                status = "needs_context"
            result = GEOSResult(
                run_id=trace.run_id,
                task=task,
                mode="nooa" if llm else "offline",
                status=status,
                repositories=names,
                contexts=contexts,
                assessments=assessments,
                validation=plan,
                proposal=proposal,
                limitations=(
                    "Source search is lexical and bounded; it is not a complete Fortran call graph.",
                    "Citation IDs are checked; the meaning of model conclusions still requires review.",
                    "No build, patch application, GEOS simulation or benchmark was run by this workflow.",
                ),
            )
            trace.artifact("result.json", result)
            trace.emit("run.completed", status=result.status)
            return result

    def _patch_inputs(self, names: tuple[str, ...]) -> list[dict[str, str | None]]:
        if len(self.targets) > 12:
            raise ValueError("At most 12 explicit patch targets are supported")
        files = []
        total = 0
        for name, relative in self.targets:
            binding = self.registry.get(name)
            if binding.name not in names:
                raise ValueError(f"Patch target {name} was not selected for this task")
            path = confined_file(binding.path, relative)
            if any(path.is_relative_to(p) for p in self.registry.excluded_roots(name)):
                raise ValueError("Patch target belongs to a different registered repository")
            if path.exists():
                content, sha = self.loader.read_file(name, relative)
            else:
                content, sha = "", None
            total += len(content)
            if total > 96000:
                raise ValueError(
                    "Complete patch input exceeds 96000 characters; select fewer files"
                )
            files.append(
                {
                    "repository": binding.name,
                    "path": relative,
                    "before_sha256": sha,
                    "content": content,
                }
            )
        return files

    @staticmethod
    def _check_proposal(proposal: PatchProposal, files: list[dict[str, str | None]]) -> None:
        allowed = {(f["repository"], f["path"]): f["before_sha256"] for f in files}
        seen = set()
        for change in proposal.changes:
            key = (change.repository, change.path)
            if key in seen or key not in allowed or change.before_sha256 != allowed[key]:
                raise ValueError("Proposal changed an unselected, duplicate or stale file")
            seen.add(key)
