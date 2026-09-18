from nexus_atom_core import Plan, Task, TaskGraph


def modernization_plan(
    *,
    proposal: str | None = None,
    software_checks: tuple[str, ...] = (),
    hypothesis="Optimize GEOS while preserving configured numerical and scientific criteria",
) -> Plan:
    if set(software_checks) - {"test", "sanitize"} or len(set(software_checks)) != len(
        software_checks
    ):
        raise ValueError("Software checks must be unique test/sanitize operations")
    operations = [
        ("inspect", "baseline"),
        ("build", "baseline"),
        *((check, "baseline") for check in software_checks),
        ("run", "baseline"),
        ("benchmark", "baseline"),
        ("profile", "baseline"),
        ("optimize", "candidate"),
        ("build", "candidate"),
        *((check, "candidate") for check in software_checks),
        ("run", "candidate"),
        ("benchmark", "candidate"),
        ("profile", "candidate"),
        ("validate", "candidate"),
        ("diagnose", "candidate"),
    ]
    return _sequential_plan(operations, proposal, hypothesis)


def _sequential_plan(operations, proposal, hypothesis):
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


def regression_plan(
    *,
    proposal: str | None = None,
    software_checks: tuple[str, ...] = (),
    hypothesis: str = "Compare baseline and candidate GEOS outputs under fixed acceptance criteria",
) -> Plan:
    """Check a prepared candidate, or compare repeated runs without source edits."""
    if set(software_checks) - {"test", "sanitize"} or len(set(software_checks)) != len(
        software_checks
    ):
        raise ValueError("Software checks must be unique test/sanitize operations")
    operations = [
        ("inspect", "baseline"),
        ("build", "baseline"),
        *((check, "baseline") for check in software_checks),
        ("run", "baseline"),
    ]
    if proposal:
        operations.append(("optimize", "candidate"))
    operations.extend(
        [
            ("build", "candidate"),
            *((check, "candidate") for check in software_checks),
            ("run", "candidate"),
            ("validate", "candidate"),
        ]
    )
    return _sequential_plan(operations, proposal, hypothesis)


gpu_port_plan = modernization_plan
optimize_plan = modernization_plan


def debug_plan():
    raise NotImplementedError(
        "Debugging requires an explicit failure-reproduction and repair policy"
    )
