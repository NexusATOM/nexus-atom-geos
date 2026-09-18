"""Explicit specialist configuration and evidence scoping, with no model calls."""

from pathlib import Path

import yaml

from geos_agents.models import GEOSTask


def load_specialists(path: Path | None):
    if path is None:
        return ()
    with path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Specialist configuration exceeds 64 KiB")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict) or set(data) != {"specialists"}:
        raise ValueError("Specialist file must contain only a specialists list")
    return GEOSTask(description="Validate specialist configuration", **data).specialists


def add_specialist_arguments(parser):
    parser.add_argument("--specialists", type=Path, help="Optional YAML specialist profiles")
    parser.add_argument("--objective-tag", action="append", default=[])


def task_specialists(args):
    return {
        "specialists": load_specialists(args.specialists),
        "objective_tags": tuple(args.objective_tag),
    }


def select_specialists(task, registry, contexts, measurements):
    """Select enabled profiles by explicit tags AND repository scope.

    No profile expands the task's repository selection. Active repository
    selectors must resolve to bindings; aliases use the registry's resolution.
    """
    selected = []
    for profile in task.specialists:
        if profile.objective_tags and not set(profile.objective_tags).intersection(
            task.objective_tags
        ):
            continue
        allowed = {registry.get(name).name for name in profile.repositories}
        scoped = tuple(
            context
            for context in contexts
            if context.evidence and (not allowed or context.repository in allowed)
        )
        if not scoped:
            continue
        names = {context.repository for context in scoped}
        timings = tuple(
            measurement
            for measurement in measurements
            if registry.get(measurement.repository).name in names
        )
        selected.append((profile, scoped, timings))
    return selected
