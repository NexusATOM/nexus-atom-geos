# nexus-atom-geos Python API

Public definitions below are generated from the shipped source. See USAGE.md and the README for runnable setup, semantics and limits. Contracts inherit strict extra-field rejection and finite-number validation where declared. Source links include the implementation for details.

## `nexus_atom_geos.config`

### `GEOSConfig`

[Source](../src/nexus_atom_geos/config.py#L10)

```python
class GEOSConfig(Contract):
    workspace: Path
    repository: str
    backend: Literal['local', 'slurm'] = 'local'
    resources: ResourceRequest = Field(default_factory=ResourceRequest)
    environment: Environment = Field(default_factory=Environment)
    commands: dict[str, tuple[str, ...]]
    phase_commands: dict[str, dict[str, tuple[str, ...]]] = Field(default_factory=dict)
    phase_resources: dict[str, ResourceRequest] = Field(default_factory=dict)
    benchmark_seconds_file: str | None = None
    dataset: str = 'results/fields.json'
    tolerance: Tolerance = Field(default_factory=Tolerance)
    science: ValidationSuite
    repeats: int = Field(default=5, ge=3, le=100)
    warmups: int = Field(default=1, ge=0, le=20)
    benchmark_identity: dict[str, str] = Field(min_length=1)
    proposal: Path | None = None
    runtime_argv: tuple[str, ...] | None = None
    nooa_model: str | None = None
    targets: tuple[tuple[str, str], ...] = ()
    def configured(self): ...
    def from_file(cls, path: Path): ...
```

## `nexus_atom_geos.demo`

A real local lifecycle over a synthetic kernel, never GEOS benchmark evidence.

### `prepare_demo`

[Source](../src/nexus_atom_geos/demo.py#L14)

```python
def prepare_demo(destination: Path) -> GEOSConfig: ...
```

## `nexus_atom_geos.examples`

Synthetic plugin examples for Phase II; no upstream model execution claimed.

### `Simulation`

[Source](../src/nexus_atom_geos/examples.py#L18)

```python
class Simulation(Capability):
    def __init__(self, system, operation, field, units): ...
    async def execute(self, task, context): ...
```

### `ToyEvaluator`

[Source](../src/nexus_atom_geos/examples.py#L41)

```python
class ToyEvaluator(Evaluator):
    def __init__(self, system): ...
    async def evaluate(self, goal, results, directory): ...
```

### `ExampleModel`

[Source](../src/nexus_atom_geos/examples.py#L59)

```python
class ExampleModel(ModelPlugin):
    def capabilities(self): ...
    def evaluators(self): ...
    def goal_constraints(self): ...
    def demo(cls, directory): ...
    async def plan(self, goal, history, registry): ...
```

### `ECCOExample`

[Source](../src/nexus_atom_geos/examples.py#L82)

```python
class ECCOExample(ExampleModel):
```

### `LISExample`

[Source](../src/nexus_atom_geos/examples.py#L86)

```python
class LISExample(ExampleModel):
```

### `ISSMExample`

[Source](../src/nexus_atom_geos/examples.py#L90)

```python
class ISSMExample(ExampleModel):
```

### `ModelEExample`

[Source](../src/nexus_atom_geos/examples.py#L94)

```python
class ModelEExample(ExampleModel):
```

## `nexus_atom_geos.plugin`

GEOS capabilities over preserved federation tooling, HPC and generic science.

### `write_json`

[Source](../src/nexus_atom_geos/plugin.py#L34)

```python
def write_json(path: Path, value): ...
```

### `log_excerpt`

[Source](../src/nexus_atom_geos/plugin.py#L40)

Bound prompt material while retaining both initial context and final errors.

```python
def log_excerpt(path: Path, limit: int=8192) -> dict: ...
```

### `GEOSCapability`

[Source](../src/nexus_atom_geos/plugin.py#L61)

```python
class GEOSCapability(Capability):
    def __init__(self, plugin, operation): ...
    async def execute(self, task, context): ...
```

### `GEOSEvaluator`

[Source](../src/nexus_atom_geos/plugin.py#L71)

```python
class GEOSEvaluator(Evaluator):
    def __init__(self, plugin, name): ...
    async def evaluate(self, goal, results, directory): ...
```

### `GEOSPlugin`

[Source](../src/nexus_atom_geos/plugin.py#L129)

```python
class GEOSPlugin(ModelPlugin):
    def __init__(self, config: GEOSConfig | None=None): ...
    def capabilities(self): ...
    def evaluators(self): ...
    async def execute(self, operation, task, context): ...
    def from_config(cls, path): ...
    def demo(cls, directory): ...
    def goal_constraints(self): ...
    async def plan(self, goal, history, registry): ...
```

## `nexus_atom_geos.workflows`

### `modernization_plan`

[Source](../src/nexus_atom_geos/workflows.py#L4)

```python
def modernization_plan(*, proposal: str | None=None, hypothesis='Optimize GEOS while preserving configured numerical and scientific criteria') -> Plan: ...
```

### `regression_plan`

[Source](../src/nexus_atom_geos/workflows.py#L39)

```python
def regression_plan() -> Plan: ...
```

### `debug_plan`

[Source](../src/nexus_atom_geos/workflows.py#L67)

```python
def debug_plan(): ...
```
