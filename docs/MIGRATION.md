# GEOS Agent migration record

This repository is the canonical home for the GEOS Agent and ATOM GEOS plugin.
No installation, example, or CI check needs the former GitHub repository.
The migration preserves both the usable implementation and its Git history.

## Coverage

The [file manifest](migration-manifest.json) accounts for all 52 tracked files
at original commit `8f1f7ec` (the 0.2.0 implementation plus the agent usage and
readiness work). At migration, 32 files were identical, 19 were adapted to the
new repository structure, and one historical lockfile was retained in history.
All original file contents remain available through the merged source commit,
including original README, packaging, security, contribution, CI, and lock data.

| Original content | Current location |
|---|---|
| All `geos_agents` modules | `src/geos_agents/`, unchanged at migration |
| All 55 agent tests | `tests/legacy/`, fixture paths adapted |
| Synthetic source and site fixtures | `examples/legacy/demo/` and `examples/legacy/site/` |
| Engineering, specialist, and installed-wheel examples | `examples/legacy/` |
| Agent usage/readiness guides | `docs/AGENTS.md`, `docs/READINESS.md` |
| API, architecture, sessions, CLI/site guides | `docs/legacy/`, commands adapted to this repository |
| Planning, release records, changelog and execution policy | `docs/legacy/` |
| License | Root Apache-2.0 `LICENSE`, identical |
| Packaging, CI, README, contribution instructions, ignore rules | Integrated into this repository's corresponding files |
| Original `uv.lock` | Preserved at the original commit and namespaced release tags; not the lock for the integrated ATOM dependency graph |

The `legacy` directories preserve origin and stable paths; the agent interfaces
remain supported. The new ATOM plugin lives alongside them in `src/nexus_atom_geos`.
Original Git history is joined to this repository without replacing its current
working tree. Annotated release tag objects are preserved under:

- `geos-agent/v0.1.0a1`
- `geos-agent/v0.1.0a2`
- `geos-agent/v0.1.0a3`
- `geos-agent/v0.1.0`
- `geos-agent/v0.2.0`

These are historical standalone releases. The existing ATOM `v0.1.0` tag is
unchanged. Historical tags retain the old standalone package metadata; use
current `main` for integrated setup and the current guides.

## Verify without the old repository

In a full clone including tags:

```bash
python scripts/check_migration.py
```

The check verifies source-history ancestry, an exhaustive original file list,
original blob hashes, destination existence, and all five preserved releases.
It needs only this repository. It does not assert that future versions of an
adapted file must remain identical to the original.

CI additionally runs the original and plugin tests, the migrated examples, and
an installed-wheel check that creates, executes, resumes, and verifies an agent
session without Controller. See [readiness](READINESS.md) for installation and
honest production-validation boundaries.

Existing GEOS Agent SQLite sessions use the same code and schema. Keep their
source checkouts and evidence at their recorded paths; copying a database alone
does not relocate its referenced files. Controller experiment stores remain a
separate format, with no automatic conversion between the two.
