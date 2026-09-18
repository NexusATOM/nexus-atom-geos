"""Controlled local capabilities and isolated Git workspaces for engineering runs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from geos_agents.context import ContextLoader, git_state
from geos_agents.execution import CommandResult, CommandRunner
from geos_agents.models import RepositoryBinding
from geos_agents.registry import RepositoryRegistry
from geos_agents.trace import RunTrace


class GEOSWorkspace:
    """Explicit repository view shared by deterministic engineering capabilities.

    No implicit shell, scheduler or network access is supplied to LLM agents.
    A site can register build, test, profiler or synchronous scheduler-wrapper
    commands in the workspace profile and invoke them by name.
    """

    def __init__(self, repositories: RepositoryRegistry, artifacts: RunTrace):
        self.repositories = repositories
        self.artifacts = artifacts
        self.context = ContextLoader(repositories)
        self.commands = CommandRunner(repositories, artifacts)

    def build(self, repository: str, command: str, *, execute: bool = False) -> CommandResult:
        spec = self.repositories.get(repository).commands.get(command)
        if spec is None or spec.purpose != "build":
            raise ValueError("Build requires a configured command with purpose: build")
        return self.commands.run(repository, command, execute=execute)

    def validate(self, repository: str, command: str, *, execute: bool = False) -> CommandResult:
        spec = self.repositories.get(repository).commands.get(command)
        if spec is None or spec.purpose != "test":
            raise ValueError("Validation requires a configured command with purpose: test")
        return self.commands.run(repository, command, execute=execute)

    def isolate(self, destination: Path) -> GEOSWorkspace:
        """Create detached worktrees, preserving nested mepo placement.

        All bound repositories must be clean, initialized Git roots. Worktrees
        persist for review; the original branches and files are never checked out
        or patched. Git's shared object/worktree metadata is necessarily updated.
        """
        bindings = list(self.repositories.bindings.values())
        if not bindings:
            raise ValueError("Cannot isolate an empty workspace")
        commits = {}
        paths = [binding.path for binding in bindings]
        if len(set(paths)) != len(paths):
            raise ValueError("Two repository bindings cannot share a checkout path")
        for binding in bindings:
            state = git_state(binding.path)
            if not state.commit or state.dirty is not False:
                raise ValueError(
                    f"Isolated work requires a clean initialized Git checkout: {binding.name}"
                )
            commits[binding.name] = state.commit
        base = Path(os.path.commonpath(paths))
        if base in paths:
            base = base.parent
        destination = destination.resolve()
        isolated = []
        for binding in sorted(bindings, key=lambda b: len(b.path.parts)):
            target = destination / binding.path.relative_to(base)
            target.parent.mkdir(parents=True, exist_ok=True)
            with self.artifacts.span(
                "worktree", repository=binding.name, path=str(target), commit=commits[binding.name]
            ):
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(binding.path),
                        "worktree",
                        "add",
                        "--detach",
                        str(target),
                        commits[binding.name],
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            isolated.append(
                RepositoryBinding(
                    name=binding.name,
                    path=target,
                    remote=binding.remote,
                    expected_ref=binding.expected_ref,
                    component=binding.component,
                    commands=binding.commands,
                )
            )
            # Persist after each allocation, so a partially failed setup is recoverable.
            self.artifacts.emit(
                "worktree.created",
                repository=binding.name,
                original=str(binding.path),
                path=str(target),
                commit=commits[binding.name],
            )
        registry = RepositoryRegistry(isolated)
        registry.write(self.artifacts.directory / "workspace.yaml")
        return GEOSWorkspace(registry, self.artifacts)
