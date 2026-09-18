"""Create a synthetic debugging configuration; no GEOS science claim or model call."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

from nexus_atom_geos.config import GEOSConfig
from nexus_atom_geos.demo import prepare_demo


def prepare(destination: Path):
    config = prepare_demo(destination)
    root = config.workspace.parent / "baseline"
    kernel = root / "kernel.py"
    kernel.write_text("def compute():\n    return -1.0\n")
    subprocess.run(["git", "-C", str(root), "add", "kernel.py"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Demo",
            "-c",
            "user.email=demo@example.invalid",
            "commit",
            "-qm",
            "Synthetic bug",
        ],
        check=True,
    )
    proposal = json.loads(config.proposal.read_text())
    proposal["changes"][0]["before_sha256"] = hashlib.sha256(kernel.read_bytes()).hexdigest()
    config.proposal.write_text(json.dumps(proposal, indent=2))
    reference = config.workspace.parent / "reference.json"
    reference.write_text(
        json.dumps(
            {
                "fields": {
                    "synthetic_mass": {
                        "units": "1",
                        "shape": [1],
                        "values": [4999950000.0],
                        "weights": [1.0],
                    }
                },
                "metadata": {"model": "synthetic-demo"},
            }
        )
    )
    data = config.model_dump(mode="json")
    data.update(
        workflow="debug",
        benchmark_identity={},
        debug={
            "reference_dataset": str(reference),
            "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            "expected_exit_code": 1,
            "failure_signature": "ATOM_EXPECTED_FAILURE",
            "protected_files": [["MAPL", "run.py"]],
        },
    )
    data["commands"] = {k: v for k, v in data["commands"].items() if k in {"build", "run"}}
    data["commands"]["reproduce"] = [
        sys.executable,
        "-c",
        "from kernel import compute; assert compute() == 4999950000.0, 'ATOM_EXPECTED_FAILURE'",
    ]
    validated = GEOSConfig.model_validate(data)
    path = config.workspace.parent / "debug.yaml"
    path.write_text(yaml.safe_dump(validated.model_dump(mode="json")))
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    print(prepare(parser.parse_args().destination))
