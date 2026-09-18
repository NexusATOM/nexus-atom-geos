"""Bind known GEOS repositories to explicit local checkouts and mepo manifests."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from geos_agents.catalog import CATALOG, resolve
from geos_agents.models import GEOSTask, RepositoryBinding


class RepositoryRegistry:
    def __init__(self, bindings: list[RepositoryBinding] | None = None):
        self.bindings: dict[str, RepositoryBinding] = {}
        for binding in bindings or []:
            try:
                name = resolve(binding.name).name
            except ValueError:
                name = binding.name
                if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name):
                    raise ValueError(f"Invalid repository name: {name}") from None
            if name.casefold() in {key.casefold() for key in self.bindings}:
                raise ValueError(f"Duplicate repository binding: {name}")
            self.bindings[name] = binding.model_copy(
                update={"name": name, "path": binding.path.expanduser().resolve()}
            )

    @classmethod
    def from_file(cls, path: Path) -> RepositoryRegistry:
        """Load workspace YAML; relative paths are relative to the YAML file."""
        path = path.resolve()
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict) or set(data) != {"repositories"}:
            raise ValueError("workspace must contain only a 'repositories' list")
        if not isinstance(data["repositories"], list):
            raise ValueError("repositories must be a list")
        bindings = []
        for raw in data["repositories"]:
            binding = RepositoryBinding.model_validate(raw)
            bindings.append(
                binding.model_copy(update={"path": path.parent / binding.path.expanduser()})
            )
        return cls(bindings)

    @classmethod
    def from_mepo(cls, fixture: Path) -> RepositoryRegistry:
        """Import all local components; catalogued repositories gain canonical aliases.

        mepo's @ directory markers are literal characters, not template syntax.
        Component nesting describes placement, not a scientific dependency edge.
        """
        fixture = fixture.resolve(strict=True)
        data = yaml.safe_load((fixture / "components.yaml").read_text())
        if not isinstance(data, dict):
            raise ValueError("components.yaml must be a mapping")
        bindings = [RepositoryBinding(name="GEOSgcm", path=fixture, component="GEOSgcm")]
        for component, config in data.items():
            if not isinstance(config, dict) or config.get("fixture"):
                continue
            remote = str(config.get("remote", ""))
            name = remote.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
            try:
                name = resolve(name or str(component)).name
            except ValueError:
                name = name or str(component)
            local = config.get("local")
            if not isinstance(local, str) or not local:
                raise ValueError(f"Missing local path for {component}")
            path = (fixture / local).resolve()
            if not path.is_relative_to(fixture) or path == fixture:
                raise ValueError(f"Component path escapes or aliases fixture: {component}")
            bindings.append(
                RepositoryBinding(
                    name=name,
                    path=path,
                    remote=remote or None,
                    component=str(component),
                    expected_ref=str(config["tag"]) if "tag" in config else None,
                )
            )
        return cls(bindings)

    def write(self, path: Path) -> None:
        """Write a portable profile with paths relative to its location where possible."""
        import os

        rows = []
        for binding in self.bindings.values():
            row = binding.model_dump(mode="json")
            row["path"] = os.path.relpath(binding.path, path.resolve().parent)
            rows.append(row)
        with path.open("x") as stream:
            yaml.safe_dump({"repositories": rows}, stream, sort_keys=False)

    def get(self, name: str) -> RepositoryBinding:
        try:
            canonical = resolve(name).name
        except ValueError:
            canonical = next(
                (key for key in self.bindings if key.casefold() == name.casefold()), name
            )
        if canonical not in self.bindings:
            raise ValueError(f"Repository {canonical} is not bound in the workspace profile")
        return self.bindings[canonical]

    def select(self, task: GEOSTask) -> tuple[str, ...]:
        """Route by explicit selection or documented keyword hints; never load all repos."""
        if task.repositories:
            selected = tuple(dict.fromkeys(self.get(name).name for name in task.repositories))
            if len(selected) > task.max_repositories:
                raise ValueError("explicit repository selection exceeds max_repositories")
            return selected
        text = task.description.casefold()
        scored = []
        for spec in CATALOG:
            if spec.name not in self.bindings:
                continue
            score = sum(
                3
                for word in (spec.name, *spec.aliases)
                if re.search(r"(?<!\w)" + re.escape(word.casefold()) + r"(?!\w)", text)
            )
            score += sum(
                1
                for word in spec.domains
                if re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text)
            )
            if score:
                scored.append((score, spec.name))
        selected = [name for _, name in sorted(scored, key=lambda item: (-item[0], item[1]))]
        if not selected and self.bindings:
            selected = ["GEOSgcm" if "GEOSgcm" in self.bindings else sorted(self.bindings)[0]]
        return tuple(selected[: task.max_repositories])

    def excluded_roots(self, name: str) -> tuple[Path, ...]:
        root = self.get(name).path
        return tuple(
            b.path for b in self.bindings.values() if b.path != root and b.path.is_relative_to(root)
        )
