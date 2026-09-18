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

The useful version is not “a bunch of agents you can chat with.” It should behave like a **GEOS engineering system** that you give an actual task to, and it takes that task through investigation, modification, execution, validation, and reporting.

For example, take a real task from your current GPU work:

> “Investigate why the GPU implementation is only 1.76× faster than CPU and identify the next optimization.”

You would run something like:

```bash
geos-agent work \
  "Investigate why the GPU implementation is only 1.76x faster \
   than CPU and implement the highest-impact safe optimization."
```

Then the framework does the engineering workflow.

### 1. GEOSAgent understands the task

It turns your request into a structured task:

```text
Goal:
    Improve GPU performance

Constraints:
    - preserve CPU numerical equivalence
    - one A100
    - current GEOS configuration
    - no scientific behavior changes

Required evidence:
    - CPU/GPU timings
    - validation results
    - git diff
    - before/after performance
```

It then decides this needs:

```text
PerformanceAgent
ArchitectureAgent
CUDAAgent
ValidationAgent
```

rather than loading every GEOS specialist.

### 2. PerformanceAgent investigates the actual run

This agent has real tools, not just an LLM prompt:

```python
class PerformanceAgent(Agent):

    workspace: GEOSWorkspace
    profiler: Profiler
    slurm: Slurm

    def run_benchmark(...):
        ...

    def profile(...):
        ...

    async def diagnose(
        self,
        profile: Profile
    ) -> PerformanceDiagnosis:
        ...
```

It could submit a Discover job, collect profiling information, inspect timers and return:

```text
FV dynamics                 210 s
Physics                     184 s
CPU pressure calculations    72 s
H2D/D2H                      43 s
Other                       92 s

Likely optimization target:
pressure logarithm/power routines
```

Now you're using agents for **actual HPC work**, not code generation.

### 3. ArchitectureAgent traces the problem

It searches across the GEOS repositories:

```text
pressure calculation
       ↓
GEOSgcm/foo.F90
       ↓
MAPL interface
       ↓
GEOSfvdycore/bar.F90
       ↓
CUDA wrapper
```

And determines:

```text
Repositories required:

GEOSgcm
GEOSfvdycore

Files required:

FV_StateMod.F90
fv_dynamics.F90
cuda_state.cpp
...
```

Only those files/repositories enter the working context.

### 4. CUDAAgent gets an isolated worktree

The framework creates something like:

```text
.worktrees/
   task-0042/
       GEOSgcm/
       GEOSfvdycore/
```

The CUDA specialist receives:

```text
TASK
Move pressure log/power operations to GPU.

CONSTRAINTS
Do not alter algorithm.
Preserve numerical equivalence.
Do not introduce additional synchronization.

FILES
<relevant source>

ARCHITECTURE FINDINGS
<dependency/call graph>

PERFORMANCE FINDINGS
<profiling evidence>
```

Then it actually edits the source.

### 5. BuildAgent builds it

Not an LLM deciding how to compile GEOS.

Deterministic code:

```python
result = build_agent.build(
    configuration="held-suarez",
    gpu=True
)
```

If compilation fails:

```text
BuildAgent
    ↓
classifies failure
    ↓
CUDAAgent
    ↓
fix
    ↓
BuildAgent
```

Maybe maximum three repair iterations.

### 6. ValidationAgent runs your real gates

This is where the system becomes valuable for GEOS.

You could encode the exact validation ladder you already use:

```text
                 Change
                   │
                   ▼
                 Build
                   │
                   ▼
              Unit/oracle
                   │
                   ▼
               Sanitizers
                   │
                   ▼
                  C24
                   │
                   ▼
                  C96
                   │
                   ▼
                 C180
                   │
                   ▼
                 C384
                   │
                   ▼
                 C576
```

If C96 fails:

```text
ValidationAgent:
    CPU/GPU divergence begins at timestep 37.

    Variable:
        PT

    Max difference:
        3.8e-7

    First affected routine:
        pressure_to_temperature()
```

That evidence goes back to the CUDA agent.

The agent doesn't simply say:

> Looks good.

It cannot declare success until your deterministic validation policy passes.

### 7. PerformanceAgent benchmarks the resulting change

Suppose it gets:

```text
BEFORE

CPU       994.22 s
GPU       601.59 s
Speedup     1.65×

AFTER

CPU       994.31 s
GPU       521.84 s
Speedup     1.91×
```

Now it has evidence that the change helped.

### 8. GEOSAgent gives you an engineering report

Your terminal could end with:

```text
GEOS Agent Task #42
────────────────────────────────────

Task
Improve GPU performance.

Status
SUCCESS

Repositories modified
GEOSfvdycore
GEOSgcm

Changes
Moved pressure logarithm/power operations
from CPU state boundary to GPU.

Validation
✓ build
✓ 864 oracle cases
✓ ASAN
✓ CUDA sanitizer
✓ C24
✓ C96
✓ C180
✓ C384
✓ C576

Numerical equivalence
PASS

Performance

                 Before       After
CPU              994.22 s     994.31 s
GPU              601.59 s     521.84 s
Speedup            1.65×        1.91×

GPU improvement
13.3%

Commits
GEOSgcm:       a13fe91
GEOSfvdycore:  4ca912e

Artifacts
profile-before/
profile-after/
validation/
diff.patch
task-report.json
```

**That is the product I would build.**

---

## It shouldn't only be for GPU work

Once you have this infrastructure, the same system can do several kinds of real GEOS engineering:

```bash
geos-agent fix \
  "C384 crashes after timestep 184 with this configuration"
```

The agents reproduce → trace → isolate → patch → build → validate.

```bash
geos-agent investigate \
  "Why does changing this MAPL field break GEOSgcm?"
```

ArchitectureAgent traces repository boundaries, interfaces and dependencies.

```bash
geos-agent explain \
  "Trace U and V from FV3 dynamics through the GEOS atmosphere"
```

It produces the call/data-flow path with actual source references.

```bash
geos-agent optimize \
  "Find unnecessary CPU-GPU transfers in FV dynamics"
```

Profiler → architecture → CUDA → validation → benchmark.

```bash
geos-agent upgrade \
  "Update this dependency and determine what breaks"
```

Dependency → build → repository specialists → validation.

And eventually:

```bash
geos-agent review <PR>
```

could understand GEOS-specific implications rather than performing a generic code review.

---

## Where the main/subagent idea becomes powerful

Imagine someone gives it:

> “GPU accelerate FV3.”

That's too large for a coding agent.

Your system can recursively decompose it:

```text
GEOSAgent
│
├─ ArchitectureAgent
│    └─ map FV3 execution
│
├─ PerformanceAgent
│    └─ establish baseline/profile
│
└─ ModernizationAgent
     │
     ├─ Task 1: wind interpolation
     │    ├─ CUDAAgent
     │    └─ ValidationAgent
     │
     ├─ Task 2: thermodynamics
     │    ├─ CUDAAgent
     │    └─ ValidationAgent
     │
     ├─ Task 3: pressure calculations
     │    ├─ CUDAAgent
     │    └─ ValidationAgent
     │
     └─ Task 4: D-grid
          ├─ CUDAAgent
          └─ ValidationAgent
```

The **main agent owns the objective**.

The **subagents own bounded engineering problems**.

The **workflows enforce the scientific/software process**.

---

## The missing abstraction is `GEOSWorkspace`

I'd actually make this the center of the implementation:

```python
class GEOSWorkspace:
    repos: RepositoryRegistry
    scheduler: SlurmClient
    build: GEOSBuildSystem
    validation: ValidationSystem
    profiler: Profiler
    artifacts: ArtifactStore
```

Then every agent receives the same controlled view of the real environment:

```python
class CUDAAgent(Agent):

    workspace: GEOSWorkspace

    async def optimize(
        self,
        task: OptimizationTask
    ) -> Patch:
        ...
```

That makes the agents capable of **doing things** rather than merely answering questions.

And it gives you an important safety boundary: agents don't automatically get arbitrary shell access. They receive controlled capabilities such as:

```python
workspace.search(...)
workspace.read(...)
workspace.patch(...)
workspace.build(...)
workspace.submit_job(...)
workspace.get_job(...)
workspace.validate(...)
workspace.benchmark(...)
workspace.git_diff(...)
```

You can decide which agents are allowed to call which operations.

---

## Your first MVP could be surprisingly small

I wouldn't start by implementing the entire grand architecture.

Start with one command:

```bash
geos-agent work "..."
```

and six components:

```text
GEOSAgent
    │
    ├── ArchitectureAgent
    ├── CodingAgent
    │      └── CUDA/Fortran expertise
    ├── BuildAgent
    ├── ValidationAgent
    └── PerformanceAgent
```

Give them access to three repositories initially:

```text
GEOSgcm
GEOSfvdycore
MAPL
```

And support one end-to-end workflow:

**Investigate → modify → build → validate → benchmark → report.**

If that can autonomously take one of the CUDA optimization tasks you've been doing and reliably move it from issue description to a validated patch, you have demonstrated something substantially more useful than another agent framework. It becomes a **GEOS-aware autonomous software engineering environment**.

Yes. Conceptually, it could feel **a lot like Codex**, but I would make the state model more explicit because you have multiple specialized agents and multiple GEOS repositories.

Codex already has several analogous ideas: resumable sessions, subagents for delegated work, repository instructions through `AGENTS.md`, and compaction for long-running trajectories. ([OpenAI Developers][1]) The newer agent APIs also explicitly represent sessions, subagents, turns, items, artifacts, and persistent execution environments. ([OpenAI Developers][2])

For GEOS, I would separate **conversation state from engineering state**.

### The central idea: one `GEOSSession`

When you start:

```bash
geos-agent
```

you create:

```text
GEOSSession #8f32
│
├── Objective
│   "Improve GEOS GPU performance"
│
├── Workspace
│   ├── GEOSgcm @ cuda-dev
│   ├── GEOSfvdycore @ cuda-dev
│   └── MAPL @ develop
│
├── Task state
│   ├── active task
│   ├── completed tasks
│   ├── hypotheses
│   └── decisions
│
├── Evidence
│   ├── benchmarks
│   ├── profiles
│   ├── validation results
│   └── build logs
│
├── Changes
│   ├── commits
│   ├── patches
│   └── worktrees
│
└── Agents
    ├── ArchitectureAgent
    ├── CUDAAgent
    ├── PerformanceAgent
    └── ValidationAgent
```

That `GEOSSession` is the **source of truth**.

The individual agents should *not* be the source of truth.

---

## Don't make agents share their chat histories

This is the architecture I would avoid:

```text
CUDAAgent conversation
        ↓
copy conversation
        ↓
ValidationAgent conversation
        ↓
copy conversation
        ↓
PerformanceAgent conversation
```

After 20 iterations, you're passing enormous amounts of stale context around.

Instead:

```text
                 GEOSSession
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
   CUDAAgent    ValidationAgent PerformanceAgent
       │             │             │
       └─────────────┼─────────────┘
                     ▼
                 GEOSSession
```

Agents **read state and write results**.

---

# Think of it as a shared blackboard

For example, your session might contain:

```python
class GEOSSessionState(BaseModel):

    objective: str

    repositories: dict[str, RepositoryState]

    current_plan: Plan

    tasks: list[Task]

    findings: list[Finding]

    decisions: list[Decision]

    changes: list[CodeChange]

    builds: list[BuildResult]

    validations: list[ValidationResult]

    benchmarks: list[BenchmarkResult]

    artifacts: list[Artifact]
```

Now suppose `PerformanceAgent` discovers:

```text
Pressure log calculations remain on CPU.

Cost:
72 seconds

Files:
GEOSgcm/...
GEOSfvdycore/...
```

It writes:

```python
Finding(
    id="F-018",
    type="performance_bottleneck",
    summary="Pressure log/power calculations remain on CPU",
    evidence=["profile-034"],
    files=[...],
)
```

The CUDA agent doesn't need the PerformanceAgent's entire conversation.

It gets:

```text
TASK

Optimize finding F-018.

RELEVANT FINDINGS

F-018:
Pressure log/power calculations remain on CPU.
Profile: profile-034
Cost: 72 s

RELEVANT FILES
...

CONSTRAINTS
Exact numerical equivalence required.
```

That's much cleaner.

---

# But agents should still have private state

I would actually use **three levels of memory**.

```text
                GEOS knowledge
               long-term memory
                     │
                     ▼
                GEOSSession
               project/task state
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
       CUDA       FV3       Validation
      private    private      private
       state      state        state
```

### 1. Agent-local state

For things specific to that specialist:

```text
CUDAAgent:

Current hypothesis:
  wrapper allocations causing synchronization

Files inspected:
  cuda_state.cpp
  cuda_wrapper.cpp

Next action:
  inspect cudaMalloc calls
```

Short-lived and mostly private.

### 2. Session state

Things everyone should know:

```text
C384 passed.
C576 passed.
Commit abc123 is current.
GPU baseline = 601.59 seconds.
Current GPU = 540.12 seconds.
```

This is authoritative.

### 3. GEOS knowledge

Things learned that should survive sessions:

```text
FV3 D-grid winds are...
MAPL owns...
C576 validation command is...
GEOSfvdycore depends on...
Discover GPU nodes use...
```

That's your persistent GEOS knowledge base.

---

# This gives you a Codex-like experience

Imagine today you run:

```bash
$ geos-agent

GEOS Agent
Workspace: ~/GEOS

> Continue optimizing FV dynamics.
```

It could respond:

```text
Resuming session geos-184.

Current state:

FV dynamics
CPU: 558.08 s
GPU: 210.21 s
Speedup: 2.65×

Full model:
~1.77×

Last completed:
✓ fused thermodynamics
✓ C384 validation
✓ C576 validation

Current investigation:
pressure logarithm/power calculations
still execute on CPU.

I'll resume from that task.
```

Then you close your laptop.

Tomorrow:

```bash
geos-agent resume
```

and it loads:

```text
session database
+
git state
+
worktree
+
artifacts
+
task graph
+
relevant agent memories
```

instead of depending solely on reconstructing everything from conversation history.

That's similar in user experience to `codex resume`, which reopens saved sessions, but your implementation would add GEOS-specific structured engineering state. ([OpenAI Developers][3])

---

# You could even use commands similar to Codex

```text
/status

Session: geos-184
Branch: cuda-modernization
Objective: GPU modernization

Tasks:
  14 completed
   1 running
   3 pending

Validation:
  C24   ✓
  C96   ✓
  C180  ✓
  C384  ✓
  C576  ✓

Latest speedup:
  FV dynamics: 2.65×
  Full model: 1.77×
```

Then:

```text
/agents
```

could show:

```text
GEOSAgent
│
├── PerformanceAgent
│      status: waiting
│
├── CUDAAgent
│      status: working
│      task: pressure routines
│
└── ValidationAgent
       status: waiting
```

And:

```text
/history
```

could show:

```text
T-031 Profile FV dynamics             ✓
T-032 Identify CPU bottlenecks        ✓
T-033 Port thermodynamics             ✓
T-034 Validate C384                   ✓
T-035 Validate C576                   ✓
T-036 Port pressure calculations      RUNNING
```

That would be very usable.

---

# The task graph is more important than chat history

This is the piece I'd emphasize.

Instead of representing the work as:

```text
message
message
message
message
message
message
```

represent it as:

```text
                   Optimize FV3
                        │
            ┌───────────┴───────────┐
            ▼                       ▼
       Profile model           Establish baseline
            │                       │
            └──────────┬────────────┘
                       ▼
              Identify bottleneck
                       │
                       ▼
                Port routine
                       │
                       ▼
                    Build
                       │
                 ┌─────┴─────┐
                 ▼           ▼
             Validate     Benchmark
                 │           │
                 └─────┬─────┘
                       ▼
                   Accepted
```

Each node has:

```python
Task(
    id="T-036",
    parent="T-030",
    assigned_to="CUDAAgent",

    status="running",

    inputs=[...],
    outputs=[...],

    findings=[...],
    artifacts=[...],

    depends_on=["T-035"],
)
```

Now an agent can crash, the model can change, the context can be compacted, or you can stop for three days.

The **engineering state survives**.

---

## And agents should communicate through typed artifacts

Rather than:

> Hey ValidationAgent, CUDAAgent said he changed something and thinks it works.

you want:

```python
CodeChange(
    id="C-17",
    repository="GEOSfvdycore",
    commit="ac421d",
    files=[...],
    description="Move pressure logarithm to GPU",
    originating_task="T-036",
)
```

Then:

```python
await validation.validate(change)
```

returns:

```python
ValidationResult(
    change="C-17",

    checks={
        "oracle": PASS,
        "sanitizer": PASS,
        "C24": PASS,
        "C96": PASS,
        "C180": PASS,
        "C384": PASS,
        "C576": PASS,
    },

    numerical_equivalence=True,
)
```

Then PerformanceAgent receives **that object**.

That is where the object-oriented approach becomes genuinely useful rather than just stylistic.

---

# I would persist it in SQLite first

You don't need a vector database and distributed state system initially.

Something as boring as:

```text
~/.geos-agent/
│
├── sessions.db
│
├── sessions/
│   └── geos-184/
│       ├── state.json
│       ├── artifacts/
│       ├── profiles/
│       ├── builds/
│       └── validation/
│
└── memory/
    ├── geos.json
    ├── fv3.json
    └── mapl.json
```

plus the actual Git worktrees:

```text
~/geos-worktrees/
    geos-184/
        GEOSgcm/
        GEOSfvdycore/
        MAPL/
```

would be plenty.

SQLite stores relationships/state.

Filesystem stores large artifacts.

Git stores source changes.

That's a very robust combination.

---

## One major difference from Codex

I wouldn't try to create a **better generic Codex**.

Codex already knows how to inspect/edit/run code, delegate to subagents, use repository-level instructions, resume sessions, and maintain long trajectories. ([OpenAI Developers][1])

Your advantage is:

```text
               Generic coding agent
                       │
                       ▼
                 GEOS Agents
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
 GEOS knowledge   HPC workflows   Science validation
```

You could even eventually use **Codex itself as one of the execution agents**.

For example:

```text
GEOSAgent
   │
   ├── ArchitectureAgent
   │
   ├── PerformanceAgent
   │
   ├── CodingAgent ─────► Codex
   │
   └── ValidationAgent
```

Your framework doesn't necessarily have to compete with coding agents.

It can be the **GEOS-aware orchestration, state, validation, and knowledge layer above them**.

And I think that's the more compelling architecture: **NOOA provides the agent/object composition, Codex or another strong coding model can provide raw coding capability, while `GEOSSession + GEOSWorkspace + TaskGraph` provide the durable intelligence that makes the whole system understand how GEOS engineering actually works.**

[1]: https://developers.openai.com/api/docs/guides/latest-model?gallery=open&galleryItem=trivia-quiz-game&model=gpt-5.3-codex&translationFallback=de-DE&utm_source=chatgpt.com "Model guidance | OpenAI API"
[2]: https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions?utm_source=chatgpt.com "Sessions | OpenAI API Reference"
[3]: https://developers.openai.com/es-419/docs/codex/cli?utm_source=chatgpt.com "Codex CLI | ChatGPT Learn"

