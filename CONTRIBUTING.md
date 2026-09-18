# Contributing

Use a branch, add tests for changed behavior, and run pytest, Ruff and package builds. Changes to Core contracts must be checked against all sibling packages. Preserve evaluator independence: model-generated conclusions are not acceptance evidence. Use synthetic fixtures in CI; do not commit credentials, site profiles, proprietary model inputs or production output datasets.

Report which workflows were actually run. Distinguish offline transport tests and synthetic examples from Discover/GEOS acceptance runs. Keep public APIs and the implementation status document accurate.
