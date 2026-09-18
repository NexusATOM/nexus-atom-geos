"""Repeated wall-clock measurements of a configured command with environment provenance."""

from __future__ import annotations

import statistics

from pydantic import Field

from geos_agents.execution import CommandResult, CommandRunner
from geos_agents.models import Contract


class BenchmarkEnvironment(Contract):
    hardware: str = Field(min_length=1)
    compiler: str = Field(min_length=1)
    resolution: str = Field(min_length=1)
    mpi_layout: str = Field(min_length=1)
    threads: int = Field(ge=1)
    dataset: str = Field(min_length=1)


class BenchmarkResult(Contract):
    environment: BenchmarkEnvironment
    warmups: int = Field(ge=0)
    samples: tuple[CommandResult, ...] = Field(min_length=2)
    median_seconds: float = Field(gt=0, allow_inf_nan=False)
    min_seconds: float = Field(gt=0, allow_inf_nan=False)
    max_seconds: float = Field(gt=0, allow_inf_nan=False)
    stdev_seconds: float = Field(ge=0, allow_inf_nan=False)
    limitations: tuple[str, ...] = (
        "Measures whole-command wall time, including process startup and output collection.",
        "Environment metadata is user-supplied; hardware and data equivalence require review.",
    )


def benchmark(
    runner: CommandRunner,
    repository: str,
    command: str,
    environment: BenchmarkEnvironment,
    *,
    repeats: int = 5,
    warmups: int = 1,
) -> BenchmarkResult:
    if not 2 <= repeats <= 100 or not 0 <= warmups <= 20:
        raise ValueError("repeats must be 2–100 and warmups 0–20")
    binding = runner.registry.get(repository)
    if command not in binding.commands or binding.commands[command].purpose != "benchmark":
        raise ValueError("Benchmark command must be configured with purpose: benchmark")
    samples = []
    for trial in range(warmups + repeats):
        runner.trace.emit("benchmark.trial", index=trial, warmup=trial < warmups)
        result = runner.run(repository, command, execute=True)
        if result.status != "passed":
            raise ValueError(f"Benchmark trial {trial} did not pass: {result.status}")
        if result.git_before != result.git_after:
            raise ValueError("Repository state changed during a benchmark trial")
        if samples and result.git_before != samples[0].git_before:
            raise ValueError("Repository state changed between benchmark trials")
        if trial >= warmups:
            samples.append(result)
    times = [sample.elapsed_seconds for sample in samples]
    return BenchmarkResult(
        environment=environment,
        warmups=warmups,
        samples=tuple(samples),
        median_seconds=statistics.median(times),
        min_seconds=min(times),
        max_seconds=max(times),
        stdev_seconds=statistics.stdev(times),
    )


def compare_benchmarks(reference: BenchmarkResult, candidate: BenchmarkResult) -> dict:
    if reference.environment != candidate.environment:
        raise ValueError("Benchmark environments differ; speedup would not be comparable")
    for result in (reference, candidate):
        if any(
            sample.status != "passed" or sample.elapsed_seconds <= 0 for sample in result.samples
        ):
            raise ValueError("All measured trials must have passed with positive elapsed time")
    # Recompute medians from measurements; do not trust an edited summary field.
    a = statistics.median(sample.elapsed_seconds for sample in reference.samples)
    b = statistics.median(sample.elapsed_seconds for sample in candidate.samples)
    return {
        "speedup": a / b,
        "reference_median_seconds": a,
        "candidate_median_seconds": b,
        "environment": reference.environment.model_dump(mode="json"),
        "interpretation": "Descriptive wall-time ratio; not a statistical significance or science claim.",
    }
