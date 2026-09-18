I think this is a strong fit for GEOS, especially because the complexity is not just “a huge codebase”; it is a **federation of repositories, components, build systems, scientific domains, and execution environments**. A flat coding agent will eventually drown in context. A hierarchical agent system gives you a natural way to encode architectural ownership.

Your `labs-OO-Agents` base is particularly appropriate because its core abstraction is already close to what you want: agents are typed Python objects, subagents can be composed as object state, deterministic Python can handle orchestration, and only selected methods need to become LLM-driven.

I would not make the first level correspond directly to every GEOS repository, though. I would use **functional/domain agents at the top**, and repository specialists underneath them.

Something like this:

```text
                    GEOSAgent
                        │
         ┌──────────────┼───────────────┐
         │              │               │
 ArchitectureAgent   BuildAgent      ScienceAgent
         │              │               │
         │              │          ┌────┴─────┐
         │              │          │          │
         │           CMakeAgent  FV3Agent  PhysicsAgent
         │
         ├── RepositoryGraphAgent
         ├── DependencyAgent
         └── InterfaceAgent

                PerformanceAgent
                       │
             ┌─────────┼─────────┐
             │         │         │
         CPUAgent   GPUAgent   MPIAgent
                       │
                CUDAKernelAgent

                  ValidationAgent
                       │
            ┌──────────┼───────────┐
            │          │           │
        UnitTest   Regression   ScienceCheck
```

Then below those, I would have **repository-bound agents**.

For example:

```text
FV3Agent
 ├── GEOSgcmRepoAgent
 ├── GEOSfvdycoreRepoAgent
 └── MAPLRepoAgent
```

The repository agent is the thing that actually understands:

```text
repo path
branch / commit
build commands
test commands
AGENTS.md
source layout
ownership boundaries
dependencies
known invariants
```

That distinction matters a lot.

## The key architecture I would use

I would give the system roughly **five agent tiers**, although they don't all have to exist at first.

```text
1. Orchestrator
   GEOSAgent

2. Cross-cutting specialists
   ArchitectureAgent
   BuildAgent
   PerformanceAgent
   ValidationAgent
   DocumentationAgent

3. Scientific/component specialists
   DynamicsAgent
   PhysicsAgent
   MAPLAgent
   IOAgent
   AssimilationAgent
   etc.

4. Repository specialists
   GEOSgcmAgent
   GEOSfvdycoreAgent
   MAPLRepoAgent
   ESMA_cmakeAgent
   etc.

5. Task specialists
   CUDAAgent
   FortranAgent
   CMakeAgent
   MPIAgent
   ProfilingAgent
   RegressionAgent
```

The important part is that **these aren't necessarily a rigid tree**.

For instance:

```text
                  FV3Agent
                 /        \
        GEOSgcmAgent    FVdycoreAgent
             \             /
              \           /
                CUDAAgent
                   │
              ValidationAgent
```

So it becomes more like a **graph of expertise** than a supervisor with 40 children.

That is much closer to how GEOS engineering actually works.

---

# What the main `GEOSAgent` should do

I would deliberately keep it relatively stupid.

It should **not write CUDA or Fortran itself**.

Its job should be:

```python
class GEOSAgent(Agent):
    architecture: ArchitectureAgent
    build: BuildAgent
    performance: PerformanceAgent
    validation: ValidationAgent
    repositories: RepositoryRegistry

    async def solve(self, task: GEOSTask) -> GEOSResult:
        """Plan and coordinate work across GEOS components."""
        ...
```

Suppose you ask:

> Port the D-grid EPV calculation to CUDA and verify numerical equivalence.

The GEOS agent might generate:

```text
1. Ask ArchitectureAgent where EPV lives and what depends on it.
2. Ask RepositoryGraphAgent which repositories/files are involved.
3. Delegate implementation to:
      FV3Agent
         -> FVdycoreRepoAgent
             -> CUDAAgent
4. Delegate testing to ValidationAgent.
5. Delegate timing analysis to PerformanceAgent.
6. Combine results.
```

This is fundamentally better than giving one Codex-like agent the whole GEOS checkout and saying “figure it out.”

---

# You should introduce a `RepositoryRegistry`

This may actually become one of the most important parts of the framework.

Something like:

```python
class RepositoryInfo(BaseModel):
    name: str
    path: Path
    remote: str
    branch: str

    languages: list[str]
    dependencies: list[str]

    build_commands: list[str]
    test_commands: list[str]

    description: str


class RepositoryRegistry:
    repos: dict[str, RepositoryInfo]
```

Then:

```python
repos["GEOSgcm"]
repos["MAPL"]
repos["GEOSfvdycore"]
repos["ESMA_cmake"]
```

Agents should **request repositories through this registry** rather than assuming they have unrestricted access to every checkout.

That gives you explicit context boundaries.

---

# I would make repository context lazy

This is important for token consumption.

Don't load:

```text
GEOSgcm
MAPL
GEOSfvdycore
GMAO_Shared
ESMA_cmake
...
```

into every conversation.

Instead:

```text
User
  ↓
GEOSAgent
  ↓
ArchitectureAgent

"EPV calculation appears to involve:
 GEOSgcm + GEOSfvdycore"

  ↓

load only those repository contexts
```

Then the context might contain:

```text
GEOSfvdycore:
    relevant files
    symbols
    git history
    AGENTS.md
    call graph

GEOSgcm:
    wrapper/interface files
```

That would solve one of the largest problems with agentic work on GEOS: **context explosion**.

---

# An agent I would absolutely build: `GEOSArchitect`

This could be extremely useful independently of coding.

Example questions:

```text
Where does surface pressure originate?

What calls this FV3 routine?

Where does this array move from CPU → GPU → CPU?

Which repositories participate in initialization?

What happens between dynamics and physics?

What owns this variable?

What is the dependency path between MAPL and GEOSgcm?
```

The architect agent could have tools such as:

```python
find_symbol()
find_callers()
find_callees()
search_repository()
inspect_git_history()
inspect_cmake_target()
repository_dependencies()
```

Over time you could construct a **GEOS software knowledge graph**.

Something like:

```text
GEOSgcm
   │
   ├── uses MAPL
   │
   └── wraps GEOSfvdycore
                 │
                 ├── FV3 dynamics
                 └── CUDA wrappers
```

And below the repository level:

```text
routine
  ↓ calls
routine
  ↓ modifies
array
  ↓ transferred_to
GPU
```

That would be incredibly valuable.

---

# For your GPU modernization work, this becomes even more interesting

You could have a specialized workflow:

```text
PerformanceAgent
      │
      ▼
ProfilerAgent
      │
      ├── detect expensive CPU regions
      ├── detect H2D/D2H traffic
      ├── detect synchronization
      └── detect allocations
      │
      ▼
GPUPlannerAgent
      │
      ▼
CUDAAgent
      │
      ▼
ValidationAgent
      │
      ├── checkpoint equality
      ├── sanitizer
      ├── C24
      ├── C96
      ├── C180
      ├── C384
      └── C576
      │
      ▼
BenchmarkAgent
```

That is almost exactly the process you have been manually doing with your GEOS CUDA work.

The difference is that now the **workflow itself becomes encoded knowledge**.

---

# I would distinguish deterministic workflows from agent reasoning

This is where OO Agents seems particularly useful.

For example, don't let an LLM decide how to run your validation suite every time.

Write:

```python
class ValidationAgent(Agent):

    async def reason_about_failure(
        self,
        result: ValidationResult,
    ) -> FailureAnalysis:
        ...

    def run_short_validation(self, workspace):
        run_c24()
        run_c96()
        run_c180()

    def run_full_validation(self, workspace):
        self.run_short_validation(workspace)
        run_c384()
        run_c576()
        run_oracle_cases()
        run_sanitizers()
```

LLM:

```text
Why did C384 diverge?
```

Python:

```text
How do we execute C384?
```

That separation is essential for trustworthy scientific software agents.

---

# I would also create a `ScientistAgent`

This sounds subtle, but coding correctness and **scientific correctness** are different.

Consider:

```text
CUDA implementation matches within tolerance.
```

A software agent says:

> good.

A science validation agent asks:

```text
Did conservation change?

Did energy drift change?

Are tendencies equivalent?

Does the answer remain stable over longer integration?

Does the optimization change reproducibility?

Is the difference physically meaningful?
```

So:

```text
ValidationAgent
 ├── SoftwareValidationAgent
 └── ScientificValidationAgent
```

could be an important distinction.

---

# You can also have persistent expert memory

Individual agents could accumulate domain knowledge.

For example:

```text
FV3Agent memory:

- D-grid winds live ...
- C-grid interpolation occurs ...
- these routines require halo exchange...
- this routine assumes pressure in Pa...
- CUDA implementation historically failed when...
```

Likewise:

```text
MAPLAgent memory
CMakeAgent memory
GEOSgcmAgent memory
```

That becomes much more useful than one global "GEOS memory."

You effectively create **institutional software memory**.

---

# One thing I would avoid

I would **not** do:

```text
GEOSAgent
 ├── Repo1Agent
 ├── Repo2Agent
 ├── Repo3Agent
 ├── Repo4Agent
 ├── Repo5Agent
 ├── Repo6Agent
 ├── Repo7Agent
 ...
```

and let the orchestrator ask everyone.

That turns into:

```text
multi-agent = expensive grep
```

and you get lots of duplicated reasoning.

Instead:

```text
Task
 ↓
Planner
 ↓
Repository/Dependency discovery
 ↓
2–3 relevant specialists
 ↓
execution
```

Agents should be activated **on demand**.

---

# I would probably structure the code like this

```text
geos-agents/
│
├── geos_agents/
│   │
│   ├── core/
│   │   ├── geos_agent.py
│   │   ├── task.py
│   │   ├── workspace.py
│   │   └── repository_registry.py
│   │
│   ├── agents/
│   │   ├── architecture/
│   │   │   ├── architect.py
│   │   │   └── dependency.py
│   │   │
│   │   ├── components/
│   │   │   ├── fv3.py
│   │   │   ├── mapl.py
│   │   │   ├── physics.py
│   │   │   └── io.py
│   │   │
│   │   ├── engineering/
│   │   │   ├── fortran.py
│   │   │   ├── cuda.py
│   │   │   ├── mpi.py
│   │   │   └── cmake.py
│   │   │
│   │   ├── performance/
│   │   │   ├── profiler.py
│   │   │   └── benchmark.py
│   │   │
│   │   └── validation/
│   │       ├── numerical.py
│   │       ├── regression.py
│   │       └── science.py
│   │
│   ├── repositories/
│   │   ├── geosgcm.py
│   │   ├── fvdycore.py
│   │   ├── mapl.py
│   │   └── ...
│   │
│   ├── tools/
│   │   ├── git.py
│   │   ├── slurm.py
│   │   ├── build.py
│   │   ├── profiler.py
│   │   └── source_graph.py
│   │
│   └── workflows/
│       ├── bugfix.py
│       ├── gpu_port.py
│       ├── performance.py
│       └── validation.py
│
└── tests/
```

That gives you three very clean concepts:

**Agents = expertise**

**Tools = capabilities**

**Workflows = reproducible engineering processes**

---

# And this could become much more than a coding agent

Eventually I can imagine:

```bash
geos-agent investigate \
    "Why is C576 slower than expected?"
```

or:

```bash
geos-agent implement \
    "Move pressure logarithm calculations to GPU"
```

or:

```bash
geos-agent explain \
    "Trace temperature from FV3 dynamics through physics"
```

or:

```bash
geos-agent validate <commit>
```

or even:

```bash
geos-agent modernize GEOSgcm \
    --target gpu \
    --constraint exact-numerics
```

The last one is where the research angle gets interesting.

You would no longer just be saying:

> An LLM can modify GEOS.

You'd be investigating:

> **Can a hierarchical software-agent organization autonomously reason across the modular architecture of a production Earth system model while preserving scientific correctness?**

That is a considerably more interesting systems/research contribution.

Given what you have already demonstrated with autonomous GEOS modernization, I think **GEOS Agents could be the logical next layer over that work** rather than a separate side project.

If I were starting it, I'd make the MVP only **6 agents**:

```text
GEOSAgent
ArchitectureAgent
RepositoryAgent
CUDAAgent
ValidationAgent
PerformanceAgent
```

and support **GEOSgcm + GEOSfvdycore + MAPL** first. Once delegation/context isolation actually provides measurable benefit, then expand the taxonomy.

One other feature I'd prioritize very early: every run should produce a **trace of delegation, repository context loaded, commands executed, patches produced, validations run, and evidence supporting the final conclusion**. NOOA already has tracing concepts, so you have a good foundation for making GEOS agent work auditable instead of opaque.

This is one of those cases where the hierarchical design isn't architecture for architecture's sake — GEOS itself already has the hierarchy you need to model.

