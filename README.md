# Nexus GEOS Agent

Evidence-driven GEOS engineering agents built on NVIDIA's
[NOOA](https://github.com/NVIDIA-NeMo/labs-OO-Agents) (`nooa`) framework.

This repository implements the design in [the planning conversation](docs/PRELIM-PLANNING.md).
See [architecture and milestones](docs/ARCHITECTURE.md) and [changelog](CHANGELOG.md).

Requires Python 3.12 or 3.13. Development setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

The initial foundation includes typed contracts, a GEOS repository catalog,
mepo workspace import, and bounded repository context. Agent workflows and
the command-line entry point follow in the next milestone.
