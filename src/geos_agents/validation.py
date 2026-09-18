"""Deterministic comparisons of explicitly supplied scalar-field datasets.

An array comparison is a software/numerical check, not scientific certification.
Scientific interpretation, approved thresholds and experiment design stay explicit.
"""

from __future__ import annotations

import math
import struct
from typing import Annotated

from pydantic import Field, StrictFloat, StrictInt, model_validator

from geos_agents.models import Contract

Number = Annotated[StrictFloat | StrictInt, Field(allow_inf_nan=False)]


class FieldData(Contract):
    units: str = Field(min_length=1)
    shape: tuple[Annotated[int, Field(strict=True, gt=0)], ...] = Field(min_length=1)
    values: tuple[Number, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def shape_matches(self):
        if math.prod(self.shape) != len(self.values):
            raise ValueError("shape does not match the number of flattened values")
        if any(not math.isfinite(float(value)) for value in self.values):
            raise ValueError("all values must be finite")
        return self


class FieldDataset(Contract):
    fields: dict[str, FieldData] = Field(min_length=1)
    metadata: dict[str, str] = Field(default_factory=dict)


class TolerancePolicy(Contract):
    atol: float = Field(default=0, ge=0, allow_inf_nan=False)
    rtol: float = Field(default=0, ge=0, allow_inf_nan=False)
    bitwise: bool = False
    conserved_fields: tuple[str, ...] = ()


class FieldComparison(Contract):
    passed: bool
    count: int
    failed_count: int
    max_absolute_error: float
    rmse: float
    sum_reference: float | None = None
    sum_candidate: float | None = None
    conservation_passed: bool | None = None


class ComparisonResult(Contract):
    passed: bool
    policy: TolerancePolicy
    fields: dict[str, FieldComparison]
    reference_metadata: dict[str, str]
    candidate_metadata: dict[str, str]
    scientific_validation: str = "not_certified"
    limitations: tuple[str, ...] = (
        "JSON values are converted to binary64; bitwise mode compares that representation, not original NetCDF storage.",
        "Conservation compares unweighted sums only; supply extensive quantities or pre-weighted fields.",
        "Passing checks is not proof of long-term stability, acceptable drift or scientific validity.",
    )


def compare_fields(
    reference: FieldDataset, candidate: FieldDataset, policy: TolerancePolicy
) -> ComparisonResult:
    if reference.fields.keys() != candidate.fields.keys():
        raise ValueError("Reference and candidate field names must match exactly")
    if set(policy.conserved_fields) - reference.fields.keys():
        raise ValueError("Conservation requested for an absent field")
    for key in ("resolution", "time_step", "mpi_layout", "valid_time"):
        if reference.metadata.get(key) != candidate.metadata.get(key):
            raise ValueError(f"Incompatible experiment metadata: {key}")
    results = {}
    for name, baseline in reference.fields.items():
        proposed = candidate.fields[name]
        if baseline.shape != proposed.shape or baseline.units != proposed.units:
            raise ValueError(f"Shape or unit mismatch for {name}")
        errors = []
        failed = 0
        for raw_a, raw_b in zip(baseline.values, proposed.values, strict=True):
            a, b = float(raw_a), float(raw_b)
            error = abs(a - b)
            threshold = policy.atol + policy.rtol * abs(a)
            if not math.isfinite(error) or not math.isfinite(threshold):
                raise ValueError(f"Numerical range overflow while comparing {name}")
            errors.append(error)
            good = (
                struct.pack("!d", a) == struct.pack("!d", b)
                if policy.bitwise
                else error <= threshold
            )
            failed += not good
        # Scale first to avoid squaring large finite errors into infinity.
        maximum = max(errors)
        rmse = (
            maximum * math.sqrt(math.fsum((e / maximum) ** 2 for e in errors) / len(errors))
            if maximum
            else 0.0
        )
        total_a = total_b = conservation = None
        if name in policy.conserved_fields:
            try:
                total_a, total_b = math.fsum(baseline.values), math.fsum(proposed.values)
            except OverflowError as exc:
                raise ValueError(f"Conservation sum overflow for {name}") from exc
            delta = abs(total_a - total_b)
            tolerance = policy.atol + policy.rtol * abs(total_a)
            if not math.isfinite(delta) or not math.isfinite(tolerance):
                raise ValueError(f"Conservation comparison overflow for {name}")
            conservation = (
                struct.pack("!d", total_a) == struct.pack("!d", total_b)
                if policy.bitwise
                else delta <= tolerance
            )
        results[name] = FieldComparison(
            passed=failed == 0 and conservation is not False,
            count=len(errors),
            failed_count=failed,
            max_absolute_error=maximum,
            rmse=rmse,
            sum_reference=total_a,
            sum_candidate=total_b,
            conservation_passed=conservation,
        )
    return ComparisonResult(
        passed=all(f.passed for f in results.values()),
        policy=policy,
        fields=results,
        reference_metadata=reference.metadata,
        candidate_metadata=candidate.metadata,
    )
