from nexus_atom_core import Plan, Task, TaskGraph


def modernization_plan(
    *,
    proposal: str | None = None,
    hypothesis="Optimize GEOS while preserving configured numerical and scientific criteria",
) -> Plan:
    operations = [
        ("inspect", "baseline"),
        ("build", "baseline"),
        ("run", "baseline"),
        ("benchmark", "baseline"),
        ("profile", "baseline"),
        ("optimize", "candidate"),
        ("build", "candidate"),
        ("run", "candidate"),
        ("benchmark", "candidate"),
        ("validate", "candidate"),
        ("diagnose", "candidate"),
    ]
    tasks = []
    for index, (operation, phase) in enumerate(operations):
        parameters = {"phase": phase}
        if proposal and operation == "optimize":
            parameters["proposal"] = proposal
        tasks.append(
            Task(
                id=f"{index:02d}-{phase}-{operation}",
                capability=f"geos.{operation}",
                parameters=parameters,
                depends_on=(tasks[-1].id,) if tasks else (),
                timeout_seconds=86400,
            )
        )
    return Plan(hypothesis=hypothesis, graph=TaskGraph(tasks=tuple(tasks)))


def regression_plan() -> Plan:
    # A no-change proposal is intentionally not substituted for regression evidence.
    return Plan(
        hypothesis="Build and run the configured GEOS baseline",
        graph=TaskGraph(
            tasks=(
                Task(id="inspect", capability="geos.inspect"),
                Task(
                    id="build",
                    capability="geos.build",
                    parameters={"phase": "baseline"},
                    depends_on=("inspect",),
                ),
                Task(
                    id="run",
                    capability="geos.run",
                    parameters={"phase": "baseline"},
                    depends_on=("build",),
                ),
            )
        ),
    )


gpu_port_plan = modernization_plan
optimize_plan = modernization_plan


def debug_plan():
    return regression_plan()
