"""Deterministic debug evidence, separate from model-generated repair hypotheses."""

import hashlib
import json

from nexus_atom_science import load_dataset

from geos_agents.context import confined_file


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def protection(registry, policy):
    return [
        {
            "repository": registry.get(repository).name,
            "path": path,
            "sha256": hashlib.sha256(
                confined_file(registry.get(repository).path, path).read_bytes()
            ).hexdigest(),
        }
        for repository, path in policy.protected_files
    ]


def prepare_debug(config, registry, evidence):
    policy = config.debug
    raw = policy.reference_dataset.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != policy.reference_sha256:
        raise ValueError("Debug reference dataset hash does not match the configured policy")
    snapshot = evidence / ("reference-input" + policy.reference_dataset.suffix)
    snapshot.write_bytes(raw)
    data = load_dataset(snapshot)
    write(evidence / "baseline-fields.json", data.model_dump(mode="json"))
    write(
        evidence / "debug-reference.json",
        {
            "kind": "operator-supplied trusted reference, not output from the failing baseline",
            "source": str(policy.reference_dataset),
            "sha256": digest,
            "snapshot": snapshot.name,
        },
    )
    write(evidence / "debug-protected.json", protection(registry, policy))


def contains_signature(path, signature):
    needle = signature.encode()
    tail = b""
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            data = tail + chunk
            if needle in data:
                return True
            tail = data[-len(needle) :]
    return False


def reproduction_matches(record, policy):
    return (
        record["status"] == "failed"
        and record["returncode"] == policy.expected_exit_code
        and record["signature_matched"]
        and record["protected_unchanged"]
    )


def repair_verified(evidence, policy):
    baseline = json.loads((evidence / "baseline-reproduce.json").read_text())
    candidate = json.loads((evidence / "candidate-reproduce.json").read_text())
    reference = json.loads((evidence / "debug-reference.json").read_text())
    snapshot = evidence / reference["snapshot"]
    return (
        reproduction_matches(baseline, policy)
        and candidate["status"] == "succeeded"
        and candidate["returncode"] == 0
        and candidate["protected_unchanged"]
        and baseline["argv"] == candidate["argv"]
        and baseline["job"]["resources"] == candidate["job"]["resources"]
        and reference["sha256"] == policy.reference_sha256
        and hashlib.sha256(snapshot.read_bytes()).hexdigest() == policy.reference_sha256
        and (evidence / "proposal.json").is_file()
    )
