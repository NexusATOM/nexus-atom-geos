from pathlib import Path
from typing import Literal

from nexus_atom_core import Contract, ResourceRequest
from nexus_atom_hpc import Environment
from nexus_atom_science import Tolerance, ValidationSuite
from pydantic import Field, model_validator


class GEOSConfig(Contract):
    workflow: Literal["modernization", "regression"] = "modernization"
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
        if self.workflow == "regression" and (self.runtime_argv or self.nooa_model):
            raise ValueError("Regression accepts prepared proposals, not model-generated changes")
        required = (
            ("build", "run", "benchmark") if self.workflow == "modernization" else ("build", "run")
        )
        for phase in ("baseline", "candidate"):
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
        if config.proposal:
            values["proposal"] = (path.parent / config.proposal).resolve()
        return config.model_copy(update=values)
