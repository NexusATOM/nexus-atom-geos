"""Independent ECCO/LIS toy tasks under one goal; no physical coupling claimed."""

import argparse
import asyncio
import json
from pathlib import Path

from nexus_atom_controller import Controller, SequencePlanner, Store
from nexus_atom_core import CapabilityRegistry, Goal, Plan, TaskGraph

from nexus_atom_geos.examples import ECCOExample, LISExample


async def run(root):
    plugins = [ECCOExample(), LISExample()]
    registry = CapabilityRegistry()
    for plugin in plugins:
        registry.register(plugin)
    goal = Goal(
        objective="Demonstrate two model plugins in one experiment",
        constraints=tuple(c for p in plugins for c in p.goal_constraints()),
    )
    plans = [await p.plan(goal, (), registry) for p in plugins]
    plan = Plan(
        hypothesis="Independent atmosphere-adjacent ocean and land toy outputs",
        graph=TaskGraph(tasks=tuple(t for p in plans for t in p.graph.tasks)),
    )
    store = Store(root)
    try:
        result = await Controller(registry, SequencePlanner([plan]), store).run(goal)
        print(json.dumps({"goal_id": goal.id, **result}, indent=2))
        return 0 if result["status"] == "succeeded" else 2
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path(".atom/multimodel"))
    raise SystemExit(asyncio.run(run(parser.parse_args().state)))
