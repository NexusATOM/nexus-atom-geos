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

Run an offline GPU-port investigation with the small synthetic teaching fixture:

```bash
geos-agent gpu-port 'Port pressure_log to CUDA' \
  --workspace examples/demo/workspace.yaml --offline
```

This writes a source inventory, validation plan and audit events to
`.geos-agent/runs/<run-id>/`. The fixture is **not real GEOS source or a scientific
benchmark**. See [usage](docs/USAGE.md) for a real workspace and model setup.
