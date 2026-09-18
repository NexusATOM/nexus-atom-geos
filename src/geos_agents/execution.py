"""Run only named, user-configured commands; dry-run unless explicitly enabled.

Argument vectors avoid shell interpolation, but the commands themselves are
trusted executable code. This runner is not an operating-system sandbox.
"""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
from typing import Literal

from pydantic import Field

from geos_agents.context import confined_file, git_state
from geos_agents.models import CommandSpec, Contract, GitState
from geos_agents.registry import RepositoryRegistry
from geos_agents.trace import RunTrace


class CommandResult(Contract):
    repository: str
    command: str
    spec: CommandSpec
    git_before: GitState
    git_after: GitState
    status: Literal["dry_run", "passed", "failed", "timed_out", "output_limit"]
    returncode: int | None = None
    elapsed_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    output: str = ""


class CommandRunner:
    def __init__(
        self, registry: RepositoryRegistry, trace: RunTrace, *, max_output_bytes: int = 1_048_576
    ):
        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        self.registry = registry
        self.trace = trace
        self.max_output_bytes = max_output_bytes

    def run(self, repository: str, command: str, *, execute: bool = False) -> CommandResult:
        binding = self.registry.get(repository)
        if command not in binding.commands:
            raise ValueError(f"Command {command!r} is not configured for {binding.name}")
        spec = binding.commands[command]
        cwd = binding.path if spec.cwd == "." else confined_file(binding.path, spec.cwd)
        if not cwd.is_dir():
            raise ValueError(f"Command working directory does not exist: {cwd}")
        if any(cwd.is_relative_to(p) for p in self.registry.excluded_roots(repository)):
            raise ValueError("Command working directory belongs to another bound repository")
        before = git_state(binding.path)
        with self.trace.span(
            "command",
            repository=binding.name,
            command=command,
            argv=list(spec.argv),
            cwd=str(cwd),
            execute=execute,
            timeout_seconds=spec.timeout_seconds,
        ):
            if not execute:
                result = CommandResult(
                    repository=binding.name,
                    command=command,
                    spec=spec,
                    git_before=before,
                    git_after=before,
                    status="dry_run",
                )
            else:
                if os.name != "posix":
                    raise ValueError("Command execution requires a POSIX host (Linux or macOS)")
                started = time.monotonic()
                data = bytearray()
                status = None
                with subprocess.Popen(
                    spec.argv,
                    cwd=cwd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                ) as process:
                    try:
                        with selectors.DefaultSelector() as selector:
                            selector.register(process.stdout, selectors.EVENT_READ)
                            while selector.get_map():
                                remaining = spec.timeout_seconds - (time.monotonic() - started)
                                if remaining <= 0:
                                    status = "timed_out"
                                    break
                                for key, _ in selector.select(min(remaining, 0.1)):
                                    chunk = os.read(key.fileobj.fileno(), 65536)
                                    if not chunk:
                                        selector.unregister(key.fileobj)
                                        continue
                                    room = self.max_output_bytes - len(data)
                                    data.extend(chunk[:room])
                                    if len(chunk) > room:
                                        status = "output_limit"
                                        break
                                if status:
                                    break
                        if status is None:
                            remaining = max(
                                0.001, spec.timeout_seconds - (time.monotonic() - started)
                            )
                            try:
                                process.wait(timeout=remaining)
                            except subprocess.TimeoutExpired:
                                status = "timed_out"
                    finally:
                        # Kill the whole process group, including descendants that retained pipes.
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait()
                result = CommandResult(
                    repository=binding.name,
                    command=command,
                    spec=spec,
                    git_before=before,
                    git_after=git_state(binding.path),
                    status=status or ("passed" if process.returncode == 0 else "failed"),
                    returncode=process.returncode,
                    elapsed_seconds=time.monotonic() - started,
                    output=data.decode("utf-8", errors="replace"),
                )
            self.trace.emit("command.result", **result.model_dump(mode="json"))
            return result
