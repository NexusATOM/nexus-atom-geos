from pathlib import Path
from typing import Literal

from nexus_atom_core import Contract, ResourceRequest
from nexus_atom_hpc import Environment
from nexus_atom_science import Tolerance, ValidationSuite
from pydantic import Field, model_validator

from geos_agents.models import GEOSTask, ObjectiveTag, SpecialistProfile


class DebugPolicy(Contract):
    reference_dataset: Path
    reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_exit_code: int = Field(ge=1, le=255)
    failure_signature: str = Field(min_length=1, max_length=256)
    signature_stream: Literal["stdout", "stderr"] = "stderr"
    protected_files: tuple[tuple[str, str], ...] = ()

    @model_validator(mode="after")
    def signature_is_meaningful(self):
        if not self.failure_signature.strip():
            raise ValueError("Failure signature must contain non-whitespace characters")
        return self


class SpecialistRuntimeConfig(Contract):
    runtime_argv: tuple[str, ...] | None = None
    nooa_model: str | None = None
    timeout_seconds: float = Field(default=120, gt=0, le=86400, allow_inf_nan=False)
    max_output_tokens: int = Field(default=4096, gt=0, le=32768)

    @model_validator(mode="after")
    def one_runtime(self):
        if bool(self.runtime_argv) == bool(self.nooa_model):
            raise ValueError("Choose exactly one specialist runtime")
        return self


class GEOSConfig(Contract):
    workflow: Literal["modernization", "regression", "debug"] = "modernization"
    debug: DebugPolicy | None = None
    continuation: Literal["original", "best_valid"] = "original"
    specialists: tuple[SpecialistProfile, ...] = Field(default=(), max_length=8)
    objective_tags: tuple[ObjectiveTag, ...] = Field(default=(), max_length=8)
    specialist_runtimes: dict[str, SpecialistRuntimeConfig] = Field(default_factory=dict)
    workspace: Path
    repository: str
    backend: Literal["local", "slurm"] = "local"
    resources: ResourceRequest = Field(default_factory=ResourceRequest)
    environment: Environment = Field(default_factory=Environment)
    commands: dict[str, tuple[str, ...]]
    software_checks: tuple[Literal["test", "sanitize"], ...] = ()
    plot_fields: tuple[str, ...] = ()
    phase_commands: dict[str, dict[str, tuple[str, ...]]] = Field(default_factory=dict)
    phase_resources: dict[str, ResourceRequest] = Field(default_factory=dict)
    benchmark_seconds_file: str | None = None
    dataset: str = "results/fields.json"
    tolerance: Tolerance = Field(default_factory=Tolerance)
    science: ValidationSuite
    repeats: int = Field(default=5, ge=3, le=100)
    warmups: int = Field(default=1, ge=0, le=20)
    benchmark_identity: dict[str, str] = Field(default_factory=dict)
    proposal: Path | None = None
    runtime_argv: tuple[str, ...] | None = None
    nooa_model: str | None = None
    targets: tuple[tuple[str, str], ...] = ()

    @model_validator(mode="after")
    def configured(self):
        GEOSTask(
            description="Configured ATOM specialists",
            specialists=self.specialists,
            objective_tags=self.objective_tags,
        )
        if set(self.specialist_runtimes) - {p.name for p in self.specialists}:
            raise ValueError("Specialist runtime refers to an unknown profile")
        if self.specialists and (
            self.workflow == "regression"
            or self.proposal
            or not self.targets
            or bool(self.runtime_argv) == bool(self.nooa_model)
        ):
            raise ValueError(
                "ATOM specialists require modernization/debug with explicit targets and one proposal runtime"
            )
        if len(set(self.plot_fields)) != len(self.plot_fields) or any(
            not name for name in self.plot_fields
        ):
            raise ValueError("Plot fields must be unique nonempty names")
        if len(set(self.software_checks)) != len(self.software_checks):
            raise ValueError("Duplicate software check")
        if set(self.phase_commands) - {"baseline", "candidate"} or set(self.phase_resources) - {
            "baseline",
            "candidate",
        }:
            raise ValueError("Unknown phase override")
        if self.continuation == "best_valid" and (
            self.workflow != "modernization"
            or self.proposal
            or not (self.runtime_argv or self.nooa_model)
            or not self.targets
        ):
            raise ValueError(
                "Best-valid continuation requires modernization with a proposal runtime"
            )
        if self.workflow == "regression" and (self.runtime_argv or self.nooa_model):
            raise ValueError("Regression accepts prepared proposals, not model-generated changes")
        if self.workflow == "debug":
            if self.debug is None or not self.commands.get("reproduce"):
                raise ValueError(
                    "Debugging requires reference/failure policy and a shared reproduce command"
                )
            if any("reproduce" in commands for commands in self.phase_commands.values()):
                raise ValueError("Debug reproducer must be identical in both phases")
            if self.phase_resources.get("baseline", self.resources) != self.phase_resources.get(
                "candidate", self.resources
            ):
                raise ValueError("Debug reproducer requires matching phase resources")
            if (
                sum(bool(value) for value in (self.proposal, self.runtime_argv, self.nooa_model))
                != 1
            ):
                raise ValueError(
                    "Debugging requires exactly one prepared proposal or repair runtime"
                )
            if not self.proposal and not self.targets:
                raise ValueError("Debug repair runtime requires explicit source targets")
        elif self.debug is not None:
            raise ValueError("Debug policy requires workflow: debug")
        required = (
            ("build", "run", "benchmark") if self.workflow == "modernization" else ("build", "run")
        )
        phases = ("candidate",) if self.workflow == "debug" else ("baseline", "candidate")
        for phase in phases:
            commands = {**self.commands, **self.phase_commands.get(phase, {})}
            if any(not commands.get(op) for op in required):
                raise ValueError(f"Configure {', '.join(required)} commands for both phases")
            if any(not commands.get(op) for op in self.software_checks):
                raise ValueError(f"Configure every required software check for {phase}")
        if self.workflow == "modernization":
            if not self.benchmark_identity:
                raise ValueError("Modernization requires a benchmark identity")
            if not self.commands.get("profile") and not self.phase_commands.get("baseline", {}).get(
                "profile"
            ):
                raise ValueError("Configure a baseline profiler command")
            if self.backend == "slurm" and not self.benchmark_seconds_file:
                raise ValueError("Slurm benchmarking requires a fresh application timing JSON file")
        return self

    @classmethod
    def from_file(cls, path: Path):
        import yaml

        config = cls.model_validate(yaml.safe_load(path.read_text()))
        values = {"workspace": (path.parent / config.workspace).resolve()}
        if config.debug:
            values["debug"] = config.debug.model_copy(
                update={
                    "reference_dataset": (path.parent / config.debug.reference_dataset).resolve()
                }
            )
        if config.proposal:
            values["proposal"] = (path.parent / config.proposal).resolve()
        return config.model_copy(update=values)
