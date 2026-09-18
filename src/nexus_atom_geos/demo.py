"""A real local lifecycle over a synthetic kernel, never GEOS benchmark evidence."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

from .config import GEOSConfig


def prepare_demo(destination: Path) -> GEOSConfig:
    destination = destination.resolve()
    root = destination / "baseline"
    root.mkdir(parents=True, exist_ok=False)
    original = "def compute():\n    total = 0\n    for i in range(100000):\n        total += i\n    return float(total)\n"
    optimized = "def compute():\n    return float(99999 * 100000 // 2)\n"
    (root / "kernel.py").write_text(original)
    (root / ".gitignore").write_text("__pycache__/\nresults/\n")
    (root / "run.py").write_text("""import json
from pathlib import Path
from kernel import compute
value=compute()
assert value == 4999950000.0
Path('results').mkdir(exist_ok=True)
Path('results/fields.json').write_text(json.dumps({'fields':{'synthetic_mass':{
'units':'1','shape':[1],'values':[value],'weights':[1.0]}},'metadata':{'model':'synthetic-demo'}}))
""")
    (root / "bench.py").write_text(
        "from kernel import compute\nfor _ in range(100):\n    compute()\n"
    )
    for argv in (
        ["git", "init", "-q", str(root)],
        ["git", "-C", str(root), "add", "."],
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Nexus ATOM Demo",
            "-c",
            "user.email=demo@example.invalid",
            "commit",
            "-qm",
            "Synthetic kernel baseline",
        ],
    ):
        subprocess.run(argv, check=True, capture_output=True)
    workspace = destination / "workspace.yaml"
    workspace.write_text(yaml.safe_dump({"repositories": [{"name": "MAPL", "path": "baseline"}]}))
    proposal = destination / "proposal.json"
    proposal.write_text(
        json.dumps(
            {
                "summary": "Replace synthetic integer loop with exact arithmetic formula",
                "changes": [
                    {
                        "repository": "MAPL",
                        "path": "kernel.py",
                        "before_sha256": hashlib.sha256(original.encode()).hexdigest(),
                        "content": optimized,
                        "rationale": "Arithmetic series identity",
                    }
                ],
                "required_validation": [
                    "Exact numerical comparison and weighted synthetic mass conservation"
                ],
            }
        )
    )
    config = GEOSConfig.model_validate(
        {
            "workspace": workspace,
            "repository": "MAPL",
            "proposal": proposal,
            "commands": {
                "build": [sys.executable, "-m", "py_compile", "kernel.py"],
                "run": [sys.executable, "run.py"],
                "profile": [sys.executable, "-m", "cProfile", "bench.py"],
                "benchmark": [sys.executable, "bench.py"],
            },
            "tolerance": {"bitwise": True},
            "science": {
                "diagnostics": [
                    {"field": "synthetic_mass", "metric": "conservation", "maximum_absolute": 0}
                ]
            },
            "benchmark_identity": {
                "model": "SYNTHETIC, NOT GEOS",
                "hardware": "local CPU",
                "python": sys.version.split()[0],
            },
            "repeats": 3,
            "warmups": 1,
        }
    )
    (destination / "geos.yaml").write_text(yaml.safe_dump(config.model_dump(mode="json")))
    return config
