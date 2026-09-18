"""Review and apply digest-guarded file replacements with rollback on write errors."""

from __future__ import annotations

import difflib
import os
import tempfile
from pathlib import Path

from geos_agents.context import confined_file, digest, git_state
from geos_agents.models import PatchProposal
from geos_agents.registry import RepositoryRegistry
from geos_agents.trace import RunTrace


def _replace(path: Path, data: bytes, mode: int = 0o644) -> None:
    """Atomic replacement of one file on the same filesystem."""
    fd, temporary = tempfile.mkstemp(prefix=".geos-agent-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class PatchManager:
    def __init__(self, registry: RepositoryRegistry, trace: RunTrace):
        self.registry = registry
        self.trace = trace

    def review(
        self, proposal: PatchProposal, *, apply: bool = False, require_clean: bool = True
    ) -> dict:
        if not proposal.changes:
            raise ValueError("Proposal has no changes")
        prepared = []
        seen = set()
        roots = {}
        with self.trace.span("patch", apply=apply):
            for change in proposal.changes:
                binding = self.registry.get(change.repository)
                if not binding.path.is_dir():
                    raise ValueError(f"Repository checkout is missing: {binding.name}")
                target = confined_file(binding.path, change.path)
                if target in seen:
                    raise ValueError("Duplicate patch path")
                seen.add(target)
                if any(
                    target.is_relative_to(p) for p in self.registry.excluded_roots(binding.name)
                ):
                    raise ValueError("Patch target belongs to another registered repository")
                # Also reject unregistered nested Git repositories.
                parent = target.parent
                while parent != binding.path:
                    if (parent / ".git").exists():
                        raise ValueError("Patch target is in a nested Git repository")
                    parent = parent.parent
                if target.exists() and (not target.is_file() or target.stat().st_size > 262144):
                    raise ValueError("Patch base must be a text file no larger than 256 KiB")
                original = target.read_bytes() if target.exists() else None
                actual = digest(original) if original is not None else None
                if actual != change.before_sha256:
                    raise ValueError(f"Stale patch base for {binding.name}:{change.path}")
                if original is not None:
                    original.decode("utf-8")
                    if b"\x00" in original:
                        raise ValueError("Binary patch bases are not supported")
                replacement = change.content.encode("utf-8")
                if len(replacement) > 262144 or b"\x00" in replacement:
                    raise ValueError("Replacement must be bounded UTF-8 text without NULs")
                prepared.append(
                    (
                        target,
                        original,
                        replacement,
                        target.stat().st_mode & 0o777 if target.exists() else 0o644,
                    )
                )
                roots[binding.name] = binding.path
            if apply:
                for name, root in roots.items():
                    state = git_state(root)
                    if not state.commit or (require_clean and state.dirty is not False):
                        raise ValueError(f"Applying patches requires a clean Git checkout: {name}")

            self.trace.artifact("proposal.json", proposal)
            diff = []
            backups = []
            for index, (_target, original, replacement, mode) in enumerate(prepared):
                change = proposal.changes[index]
                label = f"{change.repository}/{change.path}"
                for line in difflib.unified_diff(
                    (original or b"").decode().splitlines(keepends=True),
                    replacement.decode().splitlines(keepends=True),
                    fromfile=f"a/{label}" if original is not None else "/dev/null",
                    tofile=f"b/{label}",
                ):
                    diff.append(
                        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
                    )
                backups.append(
                    {
                        "repository": change.repository,
                        "path": change.path,
                        "content": original.decode() if original is not None else None,
                        "sha256": digest(original) if original is not None else None,
                        "mode": mode,
                    }
                )
            (self.trace.directory / "proposal.diff").write_text("".join(diff))
            self.trace.artifact("backups.json", backups)
            if apply:
                written = []
                directories = []
                try:
                    for target, original, replacement, mode in prepared:
                        current = target.read_bytes() if target.exists() else None
                        if current != original:
                            raise ValueError(f"File changed after patch preflight: {target}")
                        missing = []
                        parent = target.parent
                        while not parent.exists():
                            missing.append(parent)
                            parent = parent.parent
                        for directory in reversed(missing):
                            directory.mkdir()
                            directories.append(directory)
                        _replace(target, replacement, mode)
                        written.append((target, original, mode))
                except BaseException:
                    for target, original, mode in reversed(written):
                        if original is None:
                            target.unlink()
                        else:
                            _replace(target, original, mode)
                    for directory in reversed(directories):
                        directory.rmdir()
                    self.trace.emit("patch.rolled_back", files=len(written))
                    raise
            result = {
                "status": "applied" if apply else "reviewed",
                "files": len(prepared),
                "diff": str(self.trace.directory / "proposal.diff"),
                "scientific_validation": "not_run",
            }
            self.trace.emit("patch.result", **result)
            return result
