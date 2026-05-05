# Forge Agents

## Public Workflow Roles

Forge exposes a small set of top-level roles:

### PlannerAgent

File: `src/agents/planner.py`

Responsibilities:

- analyze the spec
- choose the stack
- define directory structure
- emit ordered builder tasks

Important outputs:

- `decisions`
- `TaskPlanArtifact`

### BuilderAgent

File: `src/agents/builder.py`

Responsibilities:

- execute implementation tasks
- route internally by specialization
- publish code and build output artifacts

Builder specializations:

- `setup`
- `backend`
- `frontend`
- `ci`
- `deploy`
- `integration`

Important outputs:

- `CodeArtifact`
- `BuildOutputArtifact`
- contract registration for backend work

### ReviewerAgent

File: `src/agents/reviewer.py`

Responsibilities:

- inspect generated files
- validate cross-file consistency
- emit structured findings
- trigger targeted rework

Important outputs:

- `ReviewArtifact`
- `ReviewFindingArtifact`
- `ReworkRequestArtifact`

### Verifier

Files: `src/verification/`

This is a deterministic subsystem rather than an LLM agent.

Responsibilities:

- run machine checks after review
- produce structured pass/fail results
- stop the pipeline on hard verification failures

Important outputs:

- `VerificationArtifact`
- `VerificationReport`

---

## Internal Builder Generators

These are implementation helpers behind `BuilderAgent`, not top-level workflow
roles:

- `CoderAgent`
- `BackendAgent`
- `FrontendAgent`
- `CIAgent`
- `DeployAgent`

They are still useful because different implementation slices need different
prompts and generation strategies, but the orchestrator no longer treats them
as separate public pipeline stages.

---

## Optional Cross-Cutting Security

### SecurityAgent

File: `src/agents/security_agent.py`

Security is still available as a specialized analyzer, but it is not part of a
separate orchestration mode. It can be used as a focused review/hardening pass
inside the single Forge workflow.

---

## How Roles Communicate

Roles communicate through persisted, machine-readable artifacts:

- planner -> builder: task plans and decisions
- builder -> reviewer/verifier: code, logs, contracts, output manifests
- reviewer -> builder: findings and rework requests
- verifier -> orchestrator/builder: verification results

The control plane moves artifacts between roles. Roles do not rely on direct
agent-to-agent chat.
