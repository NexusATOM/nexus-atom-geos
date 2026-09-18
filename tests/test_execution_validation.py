import math
import sys

import pytest
from pydantic import ValidationError

from geos_agents.benchmark import BenchmarkEnvironment, benchmark, compare_benchmarks
from geos_agents.execution import CommandRunner
from geos_agents.models import CommandSpec, RepositoryBinding
from geos_agents.registry import RepositoryRegistry
from geos_agents.trace import RunTrace
from geos_agents.validation import FieldData, FieldDataset, TolerancePolicy, compare_fields


def make_runner(tmp_path, code, timeout=2, limit=4096):
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    registry = RepositoryRegistry(
        [
            RepositoryBinding(
                name="MAPL",
                path=root,
                commands={
                    "test": CommandSpec(
                        argv=(sys.executable, "-c", code),
                        timeout_seconds=timeout,
                        purpose="benchmark",
                    )
                },
            )
        ]
    )
    return CommandRunner(registry, RunTrace(tmp_path / "runs"), max_output_bytes=limit)


def test_execution_is_dry_by_default(tmp_path):
    runner = make_runner(tmp_path, "from pathlib import Path; Path('executed').touch()")
    assert runner.run("MAPL", "test").status == "dry_run"
    assert not (tmp_path / "repo/executed").exists()
    with pytest.raises(ValueError, match="not configured"):
        runner.run("MAPL", "unconfigured", execute=True)
    assert runner.run("MAPL", "test", execute=True).status == "passed"
    assert (tmp_path / "repo/executed").exists()


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("print('hello')", "passed"),
        ("raise SystemExit(3)", "failed"),
        ("import time; time.sleep(10)", "timed_out"),
        ("print('x' * 100000)", "output_limit"),
        ("import os, time; os.close(1); os.close(2); time.sleep(10)", "timed_out"),
    ],
)
def test_bounded_command_outcomes(tmp_path, code, status):
    runner = make_runner(tmp_path, code, timeout=0.2)
    result = runner.run("MAPL", "test", execute=True)
    assert result.status == status
    assert result.elapsed_seconds < 3
    assert len(result.output.encode()) <= 4096


def fields(values, *, units="K", shape=None, metadata=None):
    return FieldDataset(
        fields={
            "temperature": FieldData(units=units, shape=shape or (len(values),), values=values)
        },
        metadata=metadata or {},
    )


def test_tolerance_nan_units_shape_and_failure():
    a, b = fields([100.0, 200.0]), fields([100.01, 200.0])
    assert compare_fields(a, b, TolerancePolicy(atol=0.02)).passed
    result = compare_fields(a, b, TolerancePolicy(atol=0.001))
    assert not result.passed
    assert result.fields["temperature"].failed_count == 1
    assert result.scientific_validation == "not_certified"
    for value in (math.nan, math.inf, True, "1"):
        with pytest.raises(ValidationError):
            fields([value])
    with pytest.raises(ValidationError):
        fields([1, 2], shape=(3,))
    with pytest.raises(ValueError, match="unit"):
        compare_fields(a, fields([100, 200], units="Pa"), TolerancePolicy())
    with pytest.raises(ValueError, match="metadata"):
        compare_fields(a, fields([100, 200], metadata={"resolution": "C24"}), TolerancePolicy())


def test_bitwise_signed_zero_conservation_and_large_errors():
    assert compare_fields(fields([0.0]), fields([-0.0]), TolerancePolicy()).passed
    assert not compare_fields(fields([0.0]), fields([-0.0]), TolerancePolicy(bitwise=True)).passed
    result = compare_fields(
        fields([1, 1]),
        fields([1.05, 1.05]),
        TolerancePolicy(atol=0.06, conserved_fields=("temperature",)),
    )
    assert result.fields["temperature"].failed_count == 0
    assert result.fields["temperature"].conservation_passed is False
    assert not result.passed
    assert math.isfinite(
        compare_fields(fields([1e200]), fields([0]), TolerancePolicy()).fields["temperature"].rmse
    )
    with pytest.raises(ValueError, match="overflow"):
        compare_fields(fields([1e308]), fields([-1e308]), TolerancePolicy())


def test_benchmark_measures_and_requires_compatible_environment(tmp_path):
    runner = make_runner(tmp_path, "print('trial')")
    env = BenchmarkEnvironment(
        hardware="test-host",
        compiler="none",
        resolution="synthetic",
        mpi_layout="1",
        threads=1,
        dataset="synthetic",
    )
    result = benchmark(runner, "MAPL", "test", env, repeats=2, warmups=1)
    assert len(result.samples) == 2
    assert result.median_seconds > 0
    assert compare_benchmarks(result, result)["speedup"] == 1
    with pytest.raises(ValueError, match="environments"):
        compare_benchmarks(
            result,
            result.model_copy(update={"environment": env.model_copy(update={"hardware": "other"})}),
        )
    with pytest.raises(ValueError, match="repeats"):
        benchmark(runner, "MAPL", "test", env, repeats=0)


def test_failed_trial_never_becomes_benchmark(tmp_path):
    runner = make_runner(tmp_path, "raise SystemExit(1)")
    env = BenchmarkEnvironment(
        hardware="test",
        compiler="none",
        resolution="demo",
        mpi_layout="1",
        threads=1,
        dataset="demo",
    )
    with pytest.raises(ValueError, match="did not pass"):
        benchmark(runner, "MAPL", "test", env, repeats=2)
