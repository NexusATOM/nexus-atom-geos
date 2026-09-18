# Contributing

Use a branch, add tests for changed behavior, and run pytest, Ruff and package builds. Changes to Core contracts must be checked against all sibling packages. Preserve evaluator independence: model-generated conclusions are not acceptance evidence. Use synthetic fixtures in CI; do not commit credentials, site profiles, proprietary model inputs or production output datasets.

Report which workflows were actually run. Distinguish offline transport tests and synthetic examples from Discover/GEOS acceptance runs. Keep public APIs and the implementation status document accurate.


The GEOS Agent is maintained in this repository alongside the ATOM plugin.
Install `[dev,nooa]`, then run `python -m pytest tests --cov=geos_agents
--cov-fail-under=80`, `ruff check src tests examples/legacy/*.py`, and
`ruff format --check src tests examples/legacy/*.py`. Both migrated demos under
`examples/legacy` should run without provider credentials. CI additionally
builds all required wheels and checks sessions using a fresh environment without
Controller. Keep [agent usage](docs/AGENTS.md) and [migration](docs/MIGRATION.md)
current when changing those interfaces.
