# nexus-atom-geos Python API

Public definitions below are generated from the shipped source. See USAGE.md and the README for runnable setup, semantics and limits. Contracts inherit strict extra-field rejection and finite-number validation where declared. Source links include the implementation for details.

## `nexus_atom_geos.config`

### `DebugPolicy`

[Source](../src/nexus_atom_geos/config.py#L10)

```python
class DebugPolicy(Contract):
    reference_dataset: Path
    reference_sha256: str = Field(pattern='^[0-9a-f]{64}$')
    expected_exit_code: int = Field(ge=1, le=255)
    failure_signature: str = Field(min_length=1, max_length=256)
    signature_stream: Literal['stdout', 'stderr'] = 'stderr'
    protected_files: tuple[tuple[str, str], ...] = ()
    def signature_is_meaningful(self): ...
```

### `GEOSConfig`

[Source](../src/nexus_atom_geos/config.py#L25)

```python
class GEOSConfig(Contract):
    workflow: Literal['modernization', 'regression', 'debug'] = 'modernization'
    debug: DebugPolicy | None = None
    continuation: Literal['original', 'best_valid'] = 'original'
    workspace: Path
    repository: str
    backend: Literal['local', 'slurm'] = 'local'
    resources: ResourceRequest = Field(default_factory=ResourceRequest)
    environment: Environment = Field(default_factory=Environment)
    commands: dict[str, tuple[str, ...]]
    software_checks: tuple[Literal['test', 'sanitize'], ...] = ()
    plot_fields: tuple[str, ...] = ()
    phase_commands: dict[str, dict[str, tuple[str, ...]]] = Field(default_factory=dict)
    phase_resources: dict[str, ResourceRequest] = Field(default_factory=dict)
    benchmark_seconds_file: str | None = None
    dataset: str = 'results/fields.json'
    tolerance: Tolerance = Field(default_factory=Tolerance)
    science: ValidationSuite
    repeats: int = Field(default=5, ge=3, le=100)
    warmups: int = Field(default=1, ge=0, le=20)
    benchmark_identity: dict[str, str] = Field(default_factory=dict)
    proposal: Path | None = None
    runtime_argv: tuple[str, ...] | None = None
    nooa_model: str | None = None
    targets: tuple[tuple[str, str], ...] = ()
    def configured(self): ...
    def from_file(cls, path: Path): ...
```

## `nexus_atom_geos.continuation`

Reconstruct a promoted candidate from verified artifacts, never a mutable worktree.

### `verified_json`

[Source](../src/nexus_atom_geos/continuation.py#L12)

```python
def verified_json(experiment, directory, path): ...
```

### `seed_candidate`

[Source](../src/nexus_atom_geos/continuation.py#L19)

```python
def seed_candidate(context, registry, evidence, targets): ...
```

### `cumulative_proposal`

[Source](../src/nexus_atom_geos/continuation.py#L74)

```python
def cumulative_proposal(seed, proposal): ...
```

## `nexus_atom_geos.debugging`

Deterministic debug evidence, separate from model-generated repair hypotheses.

### `write`

[Source](../src/nexus_atom_geos/debugging.py#L11)

```python
def write(path, value): ...
```

### `protection`

[Source](../src/nexus_atom_geos/debugging.py#L16)

```python
def protection(registry, policy): ...
```

### `prepare_debug`

[Source](../src/nexus_atom_geos/debugging.py#L29)

```python
def prepare_debug(config, registry, evidence): ...
```

### `contains_signature`

[Source](../src/nexus_atom_geos/debugging.py#L51)

```python
def contains_signature(path, signature): ...
```

### `reproduction_matches`

[Source](../src/nexus_atom_geos/debugging.py#L63)

```python
def reproduction_matches(record, policy): ...
```

### `repair_verified`

[Source](../src/nexus_atom_geos/debugging.py#L72)

```python
def repair_verified(evidence, policy): ...
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

[Source](../src/nexus_atom_geos/plugin.py#L35)

```python
def write_json(path: Path, value): ...
```

### `log_excerpt`

[Source](../src/nexus_atom_geos/plugin.py#L41)

Bound prompt material while retaining both initial context and final errors.

```python
def log_excerpt(path: Path, limit: int=8192) -> dict: ...
```

### `proposal_feedback`

[Source](../src/nexus_atom_geos/plugin.py#L65)

Bound model context while identifying the complete sealed proposal artifact.

```python
def proposal_feedback(path: Path) -> dict: ...
```

### `GEOSCapability`

[Source](../src/nexus_atom_geos/plugin.py#L78)

```python
class GEOSCapability(Capability):
    def __init__(self, plugin, operation): ...
    async def execute(self, task, context): ...
```

### `GEOSEvaluator`

[Source](../src/nexus_atom_geos/plugin.py#L88)

```python
class GEOSEvaluator(Evaluator):
    def __init__(self, plugin, name): ...
    async def evaluate(self, goal, results, directory): ...
```

### `GEOSPlugin`

[Source](../src/nexus_atom_geos/plugin.py#L171)

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
def modernization_plan(*, proposal: str | None=None, software_checks: tuple[str, ...]=(), hypothesis='Optimize GEOS while preserving configured numerical and scientific criteria') -> Plan: ...
```

### `regression_plan`

[Source](../src/nexus_atom_geos/workflows.py#L51)

Check a prepared candidate, or compare repeated runs without source edits.

```python
def regression_plan(*, proposal: str | None=None, software_checks: tuple[str, ...]=(), hypothesis: str='Compare baseline and candidate GEOS outputs under fixed acceptance criteria') -> Plan: ...
```

### `debug_plan`

[Source](../src/nexus_atom_geos/workflows.py#L85)

```python
def debug_plan(*, proposal: str | None=None, software_checks: tuple[str, ...]=(), hypothesis='Reproduce a specified failure and verify its repair against trusted reference data') -> Plan: ...
```
