"""Read-only, bounded source discovery with exact provenance and no shell execution."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

from geos_agents.models import Evidence, GitState, RepositoryContext
from geos_agents.registry import RepositoryRegistry

SKIP_DIRS = {".git", ".venv", "build", "install", "node_modules", "__pycache__", ".geos-agent"}
SOURCE_SUFFIXES = {
    ".f",
    ".f90",
    ".f95",
    ".f03",
    ".f08",
    ".h",
    ".c",
    ".cpp",
    ".cu",
    ".cuh",
    ".cmake",
    ".md",
    ".yaml",
    ".yml",
    ".rc",
    ".py",
    ".txt",
}
PRIORITY_FILES = ("AGENTS.md", "README.md", "CMakeLists.txt", "components.yaml")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def confined_file(root: Path, relative: str) -> Path:
    """Reject traversal, absolute paths, symlinks and Git/internal state access."""
    part = Path(relative)
    if (
        part.is_absolute()
        or not part.parts
        or any(p in {"..", ".git", ".geos-agent"} for p in part.parts)
    ):
        raise ValueError(f"Invalid repository-relative path: {relative}")
    current = root.resolve()
    for item in part.parts:
        current = current / item
        if current.is_symlink():
            raise ValueError(f"Symlinks are not allowed: {relative}")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes repository: {relative}")
    return current


def git_state(root: Path) -> GitState:
    if not (root / ".git").exists():
        return GitState()

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return result.stdout.strip()

    try:
        status = git("status", "--porcelain", "--untracked-files=normal")
        fingerprint = hashlib.sha256()
        fingerprint.update(
            git("diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--").encode()
        )
        # Include new proposal files, not merely their 'untracked' status.
        untracked = git("ls-files", "--others", "--exclude-standard", "-z")
        for relative in sorted(filter(None, untracked.split("\x00"))):
            path = root / relative
            fingerprint.update(relative.encode())
            if path.is_symlink():
                fingerprint.update(os.readlink(path).encode())
            elif path.is_file():
                with path.open("rb") as stream:
                    fingerprint.update(hashlib.file_digest(stream, "sha256").digest())
        return GitState(
            commit=git("rev-parse", "HEAD"),
            branch=git("rev-parse", "--abbrev-ref", "HEAD"),
            dirty=bool(status),
            worktree_sha256=fingerprint.hexdigest(),
        )
    except (OSError, subprocess.SubprocessError):
        return GitState()


class ContextLoader:
    def __init__(
        self,
        registry: RepositoryRegistry,
        *,
        max_chars: int = 24000,
        max_files: int = 4000,
        max_file_bytes: int = 262144,
        max_scan_bytes: int = 8_000_000,
    ):
        if min(max_chars, max_files, max_file_bytes, max_scan_bytes) <= 0:
            raise ValueError("context budgets must be positive")
        self.registry = registry
        self.max_chars = max_chars
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_scan_bytes = max_scan_bytes

    def load(self, name: str, query: str) -> RepositoryContext:
        binding = self.registry.get(name)
        root = binding.path
        if not root.is_dir():
            return RepositoryContext(
                repository=binding.name,
                git=GitState(),
                expected_ref=binding.expected_ref,
                notices=("Checkout is missing; bind or populate it before source analysis.",),
            )
        excluded = self.registry.excluded_roots(name)
        words = {w.casefold() for w in re.findall(r"[\w-]{3,}", query)} - {
            "the",
            "and",
            "for",
            "with",
            "from",
            "this",
            "that",
            "where",
            "does",
            "why",
            "how",
        }
        evidence: list[Evidence] = []
        used = scanned = scan_bytes = 0
        truncated = False
        notices = []

        def paths():
            for name in PRIORITY_FILES:
                yield root / name
            for directory, dirs, files in os.walk(root, followlinks=False):
                parent = Path(directory)
                dirs[:] = sorted(
                    d
                    for d in dirs
                    if d not in SKIP_DIRS
                    and not d.startswith(".")
                    and not (parent / d).is_symlink()
                    and not (parent / d / ".git").exists()
                    and (parent / d).resolve() not in excluded
                )
                for filename in sorted(files):
                    path = parent / filename
                    if parent == root and filename in PRIORITY_FILES:
                        continue
                    if not filename.startswith(".") and path.suffix.lower() in SOURCE_SUFFIXES:
                        yield path

        for path in paths():
            if not path.is_file() or path.is_symlink():
                continue
            if (
                scanned >= self.max_files
                or scan_bytes >= self.max_scan_bytes
                or used >= self.max_chars
            ):
                truncated = True
                break
            scanned += 1
            try:
                if path.stat().st_size > self.max_file_bytes:
                    truncated = True
                    continue
                with path.open("rb") as stream:
                    raw = stream.read(
                        min(self.max_file_bytes, self.max_scan_bytes - scan_bytes) + 1
                    )
                if len(raw) > min(self.max_file_bytes, self.max_scan_bytes - scan_bytes):
                    truncated = True
                    continue
                scan_bytes += len(raw)
                content = raw.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "\x00" in content:
                continue
            lines = content.splitlines()
            relative = path.relative_to(root).as_posix()
            priority = relative in PRIORITY_FILES or path.name == "AGENTS.md"
            indices = [
                i for i, line in enumerate(lines) if any(word in line.casefold() for word in words)
            ]
            if priority:
                indices = [0] if lines else []
            if not indices:
                continue
            stop = 0
            for index in indices[:8]:
                start = max(stop, index - 3)
                end = min(len(lines), index + (50 if priority else 8))
                if start >= end:
                    continue
                excerpt_lines = []
                for line in lines[start:end]:
                    if used + len(line) + 1 > self.max_chars:
                        truncated = True
                        break
                    excerpt_lines.append(line)
                    used += len(line) + 1
                if not excerpt_lines:
                    truncated = True
                    break
                end = start + len(excerpt_lines)
                evidence.append(
                    Evidence(
                        id=f"{binding.name}:{relative}:{start + 1}-{end}",
                        repository=binding.name,
                        path=relative,
                        start_line=start + 1,
                        end_line=end,
                        sha256=digest(raw),
                        text="\n".join(excerpt_lines),
                    )
                )
                stop = end
                if priority and end < len(lines):
                    truncated = True
        if truncated:
            notices.append(
                "Context is partial: a scan, file, excerpt or character budget was reached."
            )
        if not evidence:
            notices.append("No matching source evidence found within the configured budgets.")
        return RepositoryContext(
            repository=binding.name,
            git=git_state(root),
            expected_ref=binding.expected_ref,
            evidence=tuple(evidence),
            scanned_files=scanned,
            truncated=truncated,
            notices=tuple(notices),
        )

    def read_file(self, name: str, relative: str) -> tuple[str, str]:
        """Read a complete bounded text file for a patch; snippets cannot be patch bases."""
        binding = self.registry.get(name)
        path = confined_file(binding.path, relative)
        if any(path.is_relative_to(p) for p in self.registry.excluded_roots(name)):
            raise ValueError("File belongs to another registered repository")
        with path.open("rb") as stream:
            raw = stream.read(self.max_file_bytes + 1)
        if len(raw) > self.max_file_bytes or b"\x00" in raw:
            raise ValueError("File is too large or is not text")
        return raw.decode("utf-8"), digest(raw)
