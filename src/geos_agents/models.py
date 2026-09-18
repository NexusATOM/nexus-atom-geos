"""Serializable contracts shared by tools, workflows, and NOOA generation methods."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Workflow(StrEnum):
    INVESTIGATE = "investigate"
    EXPLAIN = "explain"
    GPU_PORT = "gpu-port"
    IMPLEMENT = "implement"


class GEOSTask(Contract):
    description: str = Field(min_length=1, max_length=8000)
    workflow: Workflow = Workflow.INVESTIGATE
    repositories: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ("preserve scientific meaning",)
    max_repositories: int = Field(default=3, ge=1, le=8)

    @field_validator("description")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task description must not be blank")
        return value.strip()


class RepositorySpec(Contract):
    name: str
    remote: str
    description: str
    domains: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    source_url: str


class CommandSpec(Contract):
    argv: tuple[str, ...] = Field(min_length=1)
    cwd: str = "."
    timeout_seconds: float = Field(default=300, gt=0, le=86400, allow_inf_nan=False)
    purpose: Literal["build", "test", "benchmark", "profile"] = "test"

    @field_validator("argv")
    @classmethod
    def valid_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value[0].strip() or any("\x00" in arg for arg in value):
            raise ValueError("command arguments must have a nonempty executable and no NULs")
        return value


class RepositoryBinding(Contract):
    name: str
    path: Path
    expected_ref: str | None = None
    component: str | None = None
    commands: dict[str, CommandSpec] = Field(default_factory=dict)


class GitState(Contract):
    commit: str | None = None
    branch: str | None = None
    dirty: bool | None = None
    worktree_sha256: str | None = None


class Evidence(Contract):
    id: str
    repository: str
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    sha256: str
    text: str


class RepositoryContext(Contract):
    repository: str
    git: GitState
    expected_ref: str | None = None
    evidence: tuple[Evidence, ...] = ()
    scanned_files: int = 0
    truncated: bool = False
    notices: tuple[str, ...] = ()


class Finding(Contract):
    summary: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    confidence: Literal["observed", "inferred"] = "inferred"


class Assessment(Contract):
    summary: str
    findings: tuple[Finding, ...] = ()
    unknowns: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()


class FileChange(Contract):
    repository: str
    path: str
    before_sha256: str | None = None
    content: str = Field(max_length=262144)
    rationale: str


class PatchProposal(Contract):
    summary: str
    changes: tuple[FileChange, ...] = Field(default=(), max_length=12)
    required_validation: tuple[str, ...] = ()


class ValidationPlan(Contract):
    software_checks: tuple[str, ...]
    scientific_checks: tuple[str, ...]
    resolutions: tuple[str, ...] = ("C24", "C96", "C180", "C384", "C576")
    limitations: tuple[str, ...]


class GEOSResult(Contract):
    run_id: str
    task: GEOSTask
    mode: Literal["offline", "nooa"]
    status: Literal["investigated", "planned", "proposed", "needs_context"]
    repositories: tuple[str, ...]
    contexts: tuple[RepositoryContext, ...]
    assessments: dict[str, Assessment]
    validation: ValidationPlan
    proposal: PatchProposal | None = None
    scientific_validation: Literal["not_run"] = "not_run"
    limitations: tuple[str, ...] = ()
