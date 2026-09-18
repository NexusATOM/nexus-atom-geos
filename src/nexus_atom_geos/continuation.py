"""Reconstruct a promoted candidate from verified artifacts, never a mutable worktree."""

import json
import subprocess
from pathlib import Path

from geos_agents.models import PatchProposal
from geos_agents.patches import PatchManager
from geos_agents.trace import RunTrace


def verified_json(experiment, directory, path):
    artifact = next((a for a in experiment.artifacts if a.path == path), None)
    if artifact is None or not artifact.verify(directory):
        raise ValueError(f"Missing or corrupted continuation artifact: {path}")
    return json.loads((directory / path).read_text())


def seed_candidate(context, registry, evidence, targets):
    parent = context.parent_experiment
    if parent is None:
        return None
    if parent.goal != context.goal.id or parent.status not in {"valid", "promoted", "baseline"}:
        raise ValueError("Continuation requires an accepted experiment from this goal")
    if not parent.evaluations or not all(e.passed for e in parent.evaluations):
        raise ValueError("Continuation parent failed acceptance")
    directory = context.directory.parent / parent.id
    original = verified_json(parent, directory, "evidence/source-commits.json")
    current = json.loads((evidence / "source-commits.json").read_text())
    if {k: v["commit"] for k, v in original.items()} != {
        k: v["commit"] for k, v in current.items()
    }:
        raise ValueError("Original source commits changed since the selected candidate")
    proposal = PatchProposal.model_validate(
        verified_json(parent, directory, "evidence/cumulative-proposal.json")
    )
    allowed = {(registry.get(repo).name, Path(path).as_posix()) for repo, path in targets}
    if any((registry.get(c.repository).name, c.path) not in allowed for c in proposal.changes):
        raise ValueError("Continuation contains changes outside configured source targets")
    trace = RunTrace(context.directory / "patches", kind="continuation")
    PatchManager(registry, trace).review(proposal, apply=True, require_clean=True)
    # Commit only in detached experiment worktrees. This supplies a clean,
    # digest-checked base for the next incremental PatchManager operation.
    for repository in {c.repository for c in proposal.changes}:
        root = registry.get(repository).path
        paths = [c.path for c in proposal.changes if c.repository == repository]
        subprocess.run(
            ["git", "-C", str(root), "add", "--", *paths], check=True, capture_output=True
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "user.name=Nexus ATOM",
                "-c",
                "user.email=atom@example.invalid",
                "commit",
                "--allow-empty",
                "-qm",
                f"Reconstruct verified candidate {parent.id}",
            ],
            check=True,
            capture_output=True,
        )
    return proposal


def cumulative_proposal(seed, proposal):
    changes = {(c.repository, c.path): c for c in seed.changes} if seed else {}
    for change in proposal.changes:
        key = (change.repository, change.path)
        changes[key] = (
            change.model_copy(update={"before_sha256": changes[key].before_sha256})
            if key in changes
            else change
        )
    return PatchProposal(
        summary=proposal.summary,
        changes=tuple(changes.values()),
        required_validation=proposal.required_validation,
    )
