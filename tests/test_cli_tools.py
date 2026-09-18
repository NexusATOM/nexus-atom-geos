import json
import sys
from pathlib import Path

import yaml

from geos_agents.cli import main
from geos_agents.context import digest


def test_cli_command_comparison_patch_and_benchmark(tmp_path, capsys):
    checkout = tmp_path / "repo"
    checkout.mkdir()
    (checkout / "source.F90").write_text("before\n")
    profile = tmp_path / "workspace.yaml"
    profile.write_text(
        yaml.safe_dump(
            {
                "repositories": [
                    {
                        "name": "MAPL",
                        "path": "repo",
                        "commands": {
                            "bench": {
                                "argv": [sys.executable, "-c", "print('ok')"],
                                "purpose": "benchmark",
                            }
                        },
                    }
                ]
            }
        )
    )
    args = ["--workspace", str(profile), "--output", str(tmp_path / "runs")]
    assert main(["run", "MAPL", "bench", *args]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"
    assert main(["run", "MAPL", "bench", *args, "--execute"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "passed"
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"fields": {"mass": {"units": "kg", "shape": [1], "values": [2]}}})
    )
    candidate = tmp_path / "candidate.json"
    candidate.write_text(
        json.dumps({"fields": {"mass": {"units": "kg", "shape": [1], "values": [3]}}})
    )
    assert main(["compare", str(baseline), str(candidate), "--output", str(tmp_path / "runs")]) == 1
    assert not json.loads(capsys.readouterr().out)["passed"]
    proposal = tmp_path / "proposal.json"
    proposal.write_text(
        json.dumps(
            {
                "summary": "Review change",
                "changes": [
                    {
                        "repository": "MAPL",
                        "path": "source.F90",
                        "before_sha256": digest(b"before\n"),
                        "content": "after\n",
                        "rationale": "test",
                    }
                ],
            }
        )
    )
    assert main(["patch", str(proposal), *args]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "reviewed"
    assert (checkout / "source.F90").read_text() == "before\n"
    env = tmp_path / "environment.json"
    env.write_text(
        json.dumps(
            {
                "hardware": "host",
                "compiler": "python",
                "resolution": "demo",
                "mpi_layout": "1",
                "threads": 1,
                "dataset": "demo",
            }
        )
    )
    assert (
        main(
            [
                "benchmark",
                "MAPL",
                "bench",
                *args,
                "--environment",
                str(env),
                "--execute",
                "--repeats",
                "2",
                "--warmups",
                "0",
            ]
        )
        == 0
    )
    measured = json.loads(capsys.readouterr().out)
    assert len(measured["samples"]) == 2
    saved = tmp_path / "benchmark.json"
    saved.write_text(json.dumps(measured))
    assert main(["benchmark-compare", str(saved), str(saved)]) == 0
    assert json.loads(capsys.readouterr().out)["speedup"] == 1


def test_cli_catalog_init_graph(tmp_path, capsys):
    assert main(["catalog"]) == 0
    assert any(r["name"] == "MAPL" for r in json.loads(capsys.readouterr().out))
    (tmp_path / "components.yaml").write_text(
        "GEOSgcm: {fixture: true}\nMAPL: {local: ./@MAPL, remote: ../MAPL.git}\n"
    )
    profile = tmp_path / "workspace.yaml"
    assert main(["init", "--mepo", str(tmp_path), "--output", str(profile)]) == 0
    capsys.readouterr()
    assert main(["graph", "--workspace", str(profile)]) == 0
    graph = json.loads(capsys.readouterr().out)
    assert {"from": "GEOSgcm", "to": "MAPL"} in graph["edges"]
    assert main(["inspect", "MAPL", "--workspace", str(profile)]) == 0
    assert json.loads(capsys.readouterr().out)["notices"]


def test_offline_cli_in_clean_process_does_not_import_nooa():
    import subprocess

    command = "from geos_agents.cli import main; main(['catalog']); import sys; assert 'nooa' not in sys.modules"
    subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        capture_output=True,
        cwd=Path(__file__).resolve().parents[1],
    )
