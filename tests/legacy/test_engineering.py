import json
import subprocess
import sys

import pytest

from geos_agents.context import digest
from geos_agents.engineering import EngineeringPolicy, EngineeringRunner
from geos_agents.models import CommandSpec, FileChange, GEOSTask, PatchProposal, RepositoryBinding
from geos_agents.registry import RepositoryRegistry


@pytest.fixture
def engineering_fixture(tmp_path):
    root = tmp_path / "MAPL"
    root.mkdir()
    (root / ".gitignore").write_text("build/\n__pycache__/\n")
    (root / "kernel.py").write_text("def compute():\n    return 2.0\n")
    (root / "test_kernel.py").write_text("""import json
from pathlib import Path
from kernel import compute
result = compute()
assert result > 0
Path('build').mkdir(exist_ok=True)
Path('build/fields.json').write_text(json.dumps({
    'fields': {'mass': {'units': 'kg', 'shape': [1], 'values': [result]}},
    'metadata': {'resolution': 'synthetic', 'time_step': '1'}
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
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ],
        check=True,
    )
    commands = {
        "build": CommandSpec(
            argv=(sys.executable, "-m", "py_compile", "kernel.py"), purpose="build"
        ),
        "test": CommandSpec(argv=(sys.executable, "test_kernel.py"), purpose="test"),
        "bench": CommandSpec(
            argv=(
                sys.executable,
                "-c",
                "from kernel import compute; [compute() for _ in range(1000)]",
            ),
            purpose="benchmark",
        ),
    }
    registry = RepositoryRegistry([RepositoryBinding(name="MAPL", path=root, commands=commands)])
    policy = EngineeringPolicy.model_validate(
        {
            "gates": [
                {"repository": "MAPL", "command": "build", "kind": "build"},
                {"repository": "MAPL", "command": "test", "kind": "validation"},
            ],
            "numerical": [
                {
                    "repository": "MAPL",
                    "output": "build/fields.json",
                    "policy": {"bitwise": True, "conserved_fields": ["mass"]},
                }
            ],
            "benchmarks": [
                {
                    "repository": "MAPL",
                    "command": "bench",
                    "repeats": 2,
                    "warmups": 0,
                    "environment": {
                        "hardware": "test-host",
                        "compiler": "python",
                        "resolution": "synthetic",
                        "mpi_layout": "1",
                        "threads": 1,
                        "dataset": "demo",
                    },
                }
            ],
        }
    )
    return registry, policy, root


def make_proposal(root, replacement):
    return PatchProposal(
        summary="Synthetic kernel change",
        changes=(
            FileChange(
                repository="MAPL",
                path="kernel.py",
                before_sha256=digest((root / "kernel.py").read_bytes()),
                content=replacement,
                rationale="test",
            ),
        ),
    )


async def test_full_engineering_lifecycle_isolated_and_measured(engineering_fixture, tmp_path):
    registry, policy, original = engineering_fixture
    source = (original / "kernel.py").read_text()
    runner = EngineeringRunner(registry, tmp_path / "runs")
    result = await runner.work(
        GEOSTask(description="Refactor synthetic kernel"),
        policy,
        execute=True,
        proposal=make_proposal(original, "def compute():\n    return 1.0 + 1.0\n"),
    )
    assert result["status"] == "validated"
    assert result["scientific_validation"] == "not_certified"
    assert len(result["attempts"][0]["benchmarks"][0]["samples"]) == 2
    assert result["attempts"][0]["numerical"][0]["passed"]
    assert (original / "kernel.py").read_text() == source
    isolated = (
        RepositoryRegistry.from_file(runner.last_trace.directory / "workspace.yaml")
        .get("MAPL")
        .path
    )
    assert isolated != original
    assert "1.0 + 1.0" in (isolated / "kernel.py").read_text()
    assert (runner.last_trace.directory / "report.md").exists()
    assert json.loads((runner.last_trace.directory / "report.json").read_text()) == result


@pytest.mark.parametrize(
    ("replacement", "expected_steps"),
    [
        ("invalid python syntax !!!\n", 1),
        ("def compute():\n    return -1.0\n", 2),
        ("def compute():\n    return 3.0\n", 2),
    ],
)
async def test_candidate_failures_never_succeed(
    engineering_fixture, tmp_path, replacement, expected_steps
):
    registry, policy, original = engineering_fixture
    runner = EngineeringRunner(registry, tmp_path / "runs")
    result = await runner.work(
        GEOSTask(description="Test failure gate"),
        policy,
        execute=True,
        proposal=make_proposal(original, replacement),
    )
    assert result["status"] == "validation_failed"
    assert len(result["attempts"][0]["gates"]) == expected_steps
    assert "benchmarks" not in result["attempts"][0]


async def test_dry_work_never_creates_worktrees(engineering_fixture, tmp_path):
    registry, policy, original = engineering_fixture
    runner = EngineeringRunner(registry, tmp_path / "runs")
    report = await runner.work(GEOSTask(description="Plan work"), policy)
    assert report["status"] == "planned"
    assert not (runner.last_trace.directory / "checkouts").exists()


async def test_no_model_or_proposal_fails_before_execution(engineering_fixture, tmp_path):
    registry, policy, original = engineering_fixture
    runner = EngineeringRunner(registry, tmp_path / "runs")
    with pytest.raises(ValueError, match="exactly one"):
        await runner.work(GEOSTask(description="Invalid work"), policy, execute=True)
    assert (
        json.loads((runner.last_trace.directory / "report.json").read_text())["status"] == "error"
    )
    assert not (runner.last_trace.directory / "checkouts").exists()


async def test_model_repair_uses_current_digests_and_has_hard_bound(
    engineering_fixture, tmp_path, monkeypatch
):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    from nooa.unifiedllm import FakeLLMClient

    registry, policy, original = engineering_fixture
    policy = policy.model_copy(update={"max_repairs": 1})
    runner = EngineeringRunner(registry, tmp_path / "runs")
    bad = "def compute():\n    return 3.0\n"
    initial = make_proposal(original, bad)
    repaired = PatchProposal(
        summary="Restore numerical behavior",
        changes=(
            FileChange(
                repository="MAPL",
                path="kernel.py",
                before_sha256=digest(bad.encode()),
                content="def compute():\n    return 1.0 + 1.0\n",
                rationale="match baseline",
            ),
        ),
    )
    assessment = json.dumps(
        {"summary": "Need targeted kernel source", "findings": [], "unknowns": ["Test required"]}
    )
    prompts = []

    class RecordingFake(FakeLLMClient):
        async def acall(self, *args, **kwargs):
            response = await super().acall(*args, **kwargs)
            prompts.append(json.dumps(self.last_messages))
            return response

    llm = RecordingFake.with_code_responses(
        [assessment] * 4 + [initial.model_dump_json(), repaired.model_dump_json()]
    )
    result = await runner.work(
        GEOSTask(description="Refactor compute in kernel", repositories=("MAPL",)),
        policy,
        execute=True,
        llm=llm,
        targets=(("MAPL", "kernel.py"),),
    )
    assert result["status"] == "validated"
    assert len(result["attempts"]) == 2
    assert llm.call_count == 6
    assert "measurement:baseline:0" in prompts[1]
    assert "median_seconds" in prompts[4]
    assert digest(bad.encode()) in prompts[5]


async def test_stale_output_cannot_pass_validation(engineering_fixture, tmp_path):
    registry, policy, original = engineering_fixture
    # Baseline emits fresh fields, but candidate's validation script exits without doing so.
    proposal = PatchProposal(
        summary="Bad validation script",
        changes=(
            FileChange(
                repository="MAPL",
                path="test_kernel.py",
                before_sha256=digest((original / "test_kernel.py").read_bytes()),
                content="pass\n",
                rationale="test",
            ),
        ),
    )
    runner = EngineeringRunner(registry, tmp_path / "runs")
    with pytest.raises(FileNotFoundError):
        await runner.work(
            GEOSTask(description="Test stale output"), policy, execute=True, proposal=proposal
        )
    report = json.loads((runner.last_trace.directory / "report.json").read_text())
    assert report["status"] == "error"


async def test_failed_baseline_and_performance_gates(engineering_fixture, tmp_path):
    registry, policy, original = engineering_fixture
    proposal = make_proposal(original, "def compute():\n    return 1.0 + 1.0\n")
    strict = policy.model_copy(
        update={
            "benchmarks": (policy.benchmarks[0].model_copy(update={"minimum_speedup": 1000000}),)
        }
    )
    runner = EngineeringRunner(registry, tmp_path / "runs")
    result = await runner.work(
        GEOSTask(description="Require impossible improvement"),
        strict,
        execute=True,
        proposal=proposal,
    )
    assert result["status"] == "performance_failed"
    binding = registry.get("MAPL")
    bad_commands = dict(
        binding.commands,
        build=CommandSpec(argv=(sys.executable, "-c", "raise SystemExit(17)"), purpose="build"),
    )
    broken = RepositoryRegistry([binding.model_copy(update={"commands": bad_commands})])
    runner = EngineeringRunner(broken, tmp_path / "runs")
    result = await runner.work(
        GEOSTask(description="Baseline failure"), policy, execute=True, proposal=proposal
    )
    assert result["status"] == "baseline_failed"
    assert not result["attempts"]


def test_nested_mepo_worktrees_preserve_placement(tmp_path):
    from geos_agents.trace import RunTrace
    from geos_agents.workspace import GEOSWorkspace

    parent = tmp_path / "GEOSgcm"
    nested = parent / "src/@MAPL"
    nested.mkdir(parents=True)
    (parent / ".gitignore").write_text("src/@MAPL/\n")
    (nested / "README.md").write_text("nested repository")
    for root in (parent, nested):
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
            check=True,
        )
    registry = RepositoryRegistry(
        [
            RepositoryBinding(name="GEOSgcm", path=parent),
            RepositoryBinding(name="MAPL", path=nested),
        ]
    )
    workspace = GEOSWorkspace(registry, RunTrace(tmp_path / "runs"))
    isolated = workspace.isolate(workspace.artifacts.directory / "checkouts")
    root = isolated.repositories.get("GEOSgcm").path
    child = isolated.repositories.get("MAPL").path
    assert child == root / "src/@MAPL"
    assert (child / "README.md").read_text() == "nested repository"
    assert (child / ".git").is_file()


def test_cli_work_dry_run(engineering_fixture, tmp_path, capsys):
    import yaml

    from geos_agents.cli import main

    registry, policy, original = engineering_fixture
    profile = tmp_path / "workspace.yaml"
    registry.write(profile)
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy.model_dump(mode="json")))
    assert (
        main(
            [
                "work",
                "Plan an optimization",
                "--workspace",
                str(profile),
                "--policy",
                str(policy_path),
                "--output",
                str(tmp_path / "runs"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "planned"
