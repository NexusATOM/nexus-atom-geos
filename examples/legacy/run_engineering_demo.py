"""Run the real engineering lifecycle on a tiny synthetic Python Git repository.

No model, GPU, compiler toolchain or GEOS data required. This proves orchestration
and gate behavior only; the timing results are NOT GEOS performance measurements.
"""

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import yaml

from geos_agents.context import digest
from geos_agents.engineering import EngineeringPolicy, EngineeringRunner
from geos_agents.models import GEOSTask, PatchProposal
from geos_agents.registry import RepositoryRegistry


async def demo(destination: Path) -> dict:
    root = destination / "source"
    root.mkdir(parents=True, exist_ok=False)
    original = "def compute():\n    total = 0\n    for i in range(50000):\n        total += i\n    return float(total)\n"
    (root / "kernel.py").write_text(original)
    (root / ".gitignore").write_text("__pycache__/\nresults/\n")
    (root / "validate.py").write_text("""import json
from pathlib import Path
from kernel import compute
value = compute()
assert value == 1249975000.0
Path("results").mkdir(exist_ok=True)
Path("results/fields.json").write_text(json.dumps({
    "fields": {"synthetic_sum": {"units": "1", "shape": [1], "values": [value]}},
    "metadata": {"resolution": "synthetic", "time_step": "1"}
}))
""")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=GEOS Agent Demo",
            "-c",
            "user.email=demo@example.invalid",
            "commit",
            "-qm",
            "Synthetic baseline",
        ],
        check=True,
    )
    commands = {
        "build": {"argv": [sys.executable, "-m", "py_compile", "kernel.py"], "purpose": "build"},
        "validate": {"argv": [sys.executable, "validate.py"], "purpose": "test"},
        "benchmark": {
            "argv": [
                sys.executable,
                "-c",
                "from kernel import compute; [compute() for _ in range(20)]",
            ],
            "purpose": "benchmark",
        },
    }
    profile = destination / "workspace.yaml"
    profile.write_text(
        yaml.safe_dump({"repositories": [{"name": "MAPL", "path": "source", "commands": commands}]})
    )
    policy_data = {
        "gates": [
            {"repository": "MAPL", "command": "build", "kind": "build"},
            {"repository": "MAPL", "command": "validate", "kind": "validation"},
        ],
        "numerical": [
            {"repository": "MAPL", "output": "results/fields.json", "policy": {"bitwise": True}}
        ],
        "benchmarks": [
            {
                "repository": "MAPL",
                "command": "benchmark",
                "repeats": 3,
                "warmups": 1,
                "environment": {
                    "hardware": "local demo host",
                    "compiler": sys.version.split()[0],
                    "resolution": "synthetic",
                    "mpi_layout": "serial",
                    "threads": 1,
                    "dataset": "integers 0 through 49999",
                },
            }
        ],
    }
    (destination / "policy.yaml").write_text(yaml.safe_dump(policy_data))
    proposal = PatchProposal.model_validate(
        {
            "summary": "Use Python's builtin sum in synthetic kernel",
            "changes": [
                {
                    "repository": "MAPL",
                    "path": "kernel.py",
                    "before_sha256": digest(original.encode()),
                    "content": "def compute():\n    return float(sum(range(50000)))\n",
                    "rationale": "Same integer sum",
                }
            ],
            "required_validation": ["Synthetic numerical check; not GEOS science validation"],
        }
    )
    (destination / "proposal.json").write_text(proposal.model_dump_json(indent=2))
    runner = EngineeringRunner(RepositoryRegistry.from_file(profile), destination / "runs")
    result = await runner.work(
        GEOSTask(description="Optimize a synthetic kernel while preserving its exact value"),
        EngineeringPolicy.model_validate(policy_data),
        execute=True,
        proposal=proposal,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": str(runner.last_trace.directory / "report.md"),
                "note": "Synthetic lifecycle demonstration; not a GEOS performance or science result.",
            },
            indent=2,
        )
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".geos-agent/demos") / uuid4().hex)
    args = parser.parse_args()
    result = asyncio.run(demo(args.output.resolve()))
    raise SystemExit(0 if result["status"] == "validated" else 1)
