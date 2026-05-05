# Forge Architecture

## System Overview

Forge is a spec-driven software factory with one public execution path:

```text
forge build
  -> Planner
  -> Builder
       setup
       backend + ci + deploy   (parallel where safe)
       frontend
       integration
  -> Reviewer
  -> Verifier
```

The control plane is deterministic. Agents do not free-form chat with each
other; they exchange machine-readable artifacts through the collaboration layer.

---

## Core Layers

### 1. CLI Layer

`src/cli.py`

- Reads `.forge/spec.md` and `.forge/rules.md`
- Resolves provider configuration
- Starts the build orchestrator
- Exposes build, status, contracts, config, dev, and fix commands

### 2. Control Plane

`src/orchestrator.py`

Responsible for:

- build phase sequencing
- model routing
- policy checks and approvals
- artifact publication
- review/fix loops
- verification
- audit and report writing
- resume behavior

### 3. Agent Layer

`src/agents/`

Public workflow roles:

- `PlannerAgent`
- `BuilderAgent`
- `ReviewerAgent`

Internal builder generators:

- `CoderAgent`
- `BackendAgent`
- `FrontendAgent`
- `CIAgent`
- `DeployAgent`

Optional cross-cutting analyzer:

- `SecurityAgent`

### 4. Collaboration Layer

`src/collaboration/`

This is the protocol between phases.

Main pieces:

- `ArtifactBus` — in-memory source of truth during a build
- `ArtifactStore` — durable JSONL + JSON snapshots under `.forge/`
- `ContractRegistry` — backend/frontend/security contract alignment

Primary artifact types:

- `TaskPlanArtifact`
- `DecisionArtifact`
- `CodeArtifact`
- `BuildOutputArtifact`
- `ReviewArtifact`
- `ReviewFindingArtifact`
- `ReworkRequestArtifact`
- `VerificationArtifact`

### 5. Verification Layer

`src/verification/`

Deterministic checks that run after review. Current framework includes:

- verifier registry
- machine-readable verification results
- structured verification reports

### 6. Security Layer

`src/security/`

- `AgenticFirewall` validates every file write
- path/content policies live in `.forge/firewall_policy.json`
- decisions are logged to `.forge/firewall_audit.log`

### 7. State and Audit

- `src/state.py` — resumable build state
- `src/audit.py` — append-only build audit and summary reports

Persisted build files include:

- `.forge/build-state.yaml`
- `.forge/build_audit.jsonl`
- `.forge/build_report.json`
- `.forge/artifacts.jsonl`
- `.forge/artifacts.json`
- `.forge/contracts.json`
- `.forge/verification.json`

---

## Scheduling Model

The scheduler runs on builder specializations, not legacy top-level agent names.

Dependency rules:

- `setup` has no dependencies
- `backend`, `ci`, `deploy` depend on `setup`
- `frontend` depends on `backend`
- `integration` depends on `backend`, `frontend`, `ci`, and `deploy`

Tasks in the same specialization run sequentially.
Independent specializations may run in parallel.

---

## Data Flow

### Planner -> Builder

Planner emits:

- stack decisions
- directory structure
- task manifests

### Builder -> Reviewer / Verifier

Builder emits:

- files
- output manifests
- contracts
- build logs

### Reviewer -> Builder

Reviewer emits:

- structured review findings
- rework requests

### Verifier -> Orchestrator / Builder

Verifier emits:

- structured verification results
- pass/fail report

---

## Design Principles

- one workflow, not multiple modes
- machine-readable artifacts over prose handoffs
- deterministic scheduling over agent improvisation
- policy and verification before autonomy claims
- durable logs for replay, debugging, and audit
