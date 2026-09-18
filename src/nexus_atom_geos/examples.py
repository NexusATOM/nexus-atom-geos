"""Synthetic plugin examples for Phase II; no upstream model execution claimed."""

import json

from nexus_atom_core import (
    Artifact,
    Capability,
    Evaluation,
    Evaluator,
    ModelPlugin,
    Plan,
    Task,
    TaskGraph,
    TaskResult,
)


class Simulation(Capability):
    def __init__(self, system, operation, field, units):
        self.name = f"{system}.{operation}"
        self.field, self.units, self.system = field, units, system

    async def execute(self, task, context):
        # Fixed toy evolution illustrates the artifact contract, not domain physics.
        output = context.directory / f"{self.system}-toy-output.json"
        data = {
            "synthetic": True,
            "field": self.field,
            "units": self.units,
            "time": [0, 1, 2],
            "values": [1.0, 1.0, 1.0],
        }
        output.write_text(json.dumps(data))
        return TaskResult(
            task_id=task.id,
            status="succeeded",
            artifacts=(Artifact.capture(output, context.directory),),
        )


class ToyEvaluator(Evaluator):
    name = "validation"

    def __init__(self, system):
        self.system = system

    async def evaluate(self, goal, results, directory):
        data = json.loads((directory / f"{self.system}-toy-output.json").read_text())
        return Evaluation(
            evaluator=self.name,
            passed=data["synthetic"] is True
            and len(data["time"]) == len(data["values"])
            and all(v == 1 for v in data["values"]),
            evidence=(f"{self.system}-toy-output.json",),
            reasons=("Synthetic contract demonstration only; not model science validation.",),
        )


class ExampleModel(ModelPlugin):
    def capabilities(self):
        return [Simulation(self.name, self.operation, self.field, self.units)]

    def evaluators(self):
        return [ToyEvaluator(self.name)]

    def goal_constraints(self):
        return (f"{self.name}.validation",)

    @classmethod
    def demo(cls, directory):
        return cls()

    async def plan(self, goal, history, registry):
        if history:
            return None
        return Plan(
            hypothesis=f"Synthetic {self.name} plugin contract example",
            graph=TaskGraph(tasks=(Task(capability=f"{self.name}.{self.operation}"),)),
        )


class ECCOExample(ExampleModel):
    name, operation, field, units = "ecco", "estimate_state", "ocean_temperature", "K"


class LISExample(ExampleModel):
    name, operation, field, units = "lis", "land_simulation", "soil_water", "kg m-2"


class ISSMExample(ExampleModel):
    name, operation, field, units = "issm", "ice_simulation", "ice_thickness", "m"


class ModelEExample(ExampleModel):
    name, operation, field, units = "modele", "climate_simulation", "surface_temperature", "K"
