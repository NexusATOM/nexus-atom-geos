# Contributing

Use Python 3.12 or 3.13 and the committed dependency lock:

```bash
uv sync --locked --extra dev
uv run ruff check src tests examples/run_engineering_demo.py
uv run ruff format --check src tests examples/run_engineering_demo.py
uv run pytest --cov=geos_agents --cov-report=term-missing --cov-fail-under=80
uv run python examples/run_engineering_demo.py
uv build
```

The test suite uses real NOOA PredictStrategy dispatch with FakeLLMClient, local
Git repositories/worktrees, and subprocesses. It requires no API key, GPU, GEOS
checkout or HPC access. Live provider tests and site-specific GEOS validation are
separate from CI and must record their environment and evidence.

Keep source gathering and execution deterministic. Add a NOOA generation method
only when the step requires reasoning. Agents must not award validation success;
only configured executed gates may do that. Test regressions with realistic
failure cases, especially stale outputs, incorrect citations, changed patch bases,
failed commands, path escapes and false performance claims.

Use `codex/` or your team's branch convention. Make focused commits and update
CHANGELOG.md for behavior changes. Before release, update both package versions,
run `uv lock`, execute the checks above, build and smoke-test the wheel, record
results in docs/RELEASE.md, commit, and create an annotated `vX.Y.Z` tag. Never move
an existing release tag. Pushing a branch, tag or publishing a package is a
separate repository-maintainer action. No automatic PyPI publication is configured.

Refresh the GEOS catalog from upstream repository descriptions and local fixture
manifests. Do not convert mepo placement into purported call dependencies. The
catalog is curated guidance; actual code evidence is required for findings.
