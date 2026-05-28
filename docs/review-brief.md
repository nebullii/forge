# Forge Technical Review Brief

Audience: senior AI/platform engineers evaluating whether Forge has a coherent,
defensible local-first architecture.

## Executive Summary

Forge is a local-first AI software builder. A user writes `.forge/spec.md`; Forge
parses structured Spec API primitives, compiles a deterministic task graph,
routes each task to role-specific models, validates generated artifacts, enforces
policy-controlled writes, and persists state, contracts, audit logs, and
verification output.

The current state is best described as a production-ready MVP for local
developer workflows and technical review. It is not positioned as a hosted SaaS
or distributed multi-tenant control plane.

## What Is Implemented

- Spec API parser and deterministic task graph compiler.
- Version dispatch for Spec API `0.1` and forward-compatible `0.2`.
- Role-aware model routing for local Ollama and OpenAI-compatible providers.
- Streaming CLI progress for planner and sequential builder/model phases.
- Builder specializations for setup, backend, frontend, CI, deploy, and general
  code generation.
- Machine-readable agent output contracts.
- Artifact bus and durable artifact store.
- Contract registry for API/model/event contracts.
- Firewall-checked writes with audit logs.
- Reviewer feedback and targeted rework loop.
- Deterministic verification layer.
- REST API plane via `forge serve`.
- Read-only local dashboard via `forge serve --ui`.
- Agent capability registry exposed at `/.well-known/agent.json`.
- Durable local job queue via `.forge/jobs.sqlite` and `forge worker`.

## Architecture In One Flow

```text
.forge/spec.md
  -> Spec API parser
  -> versioned compiler
  -> deterministic task graph
  -> model routing
  -> builder specializations
  -> artifact bus + contract registry
  -> firewall-checked writes
  -> review/rework
  -> deterministic verification
  -> state, audit, contracts, artifacts
```

## API Plane

`forge serve --port 4123 --ui` exposes local endpoints for:

- spec validation and compilation
- build and task submission
- queued jobs
- task graph inspection
- events and SSE streams
- contracts and OpenAPI export
- artifacts and audit logs
- model health and routing
- agent capability metadata

In-process jobs are the default. Passing `{"queue": true}` enqueues work in
SQLite for `forge worker`.

## Security And Reliability Posture

Forge does not grant agents direct filesystem authority. Generated writes pass
through:

- path traversal checks
- project-root confinement
- content policy checks
- audit logging
- deterministic post-generation verification

Known high-risk areas are explicitly bounded:

- model quality still affects generated application quality
- dashboard is read-only
- worker mode is local SQLite-backed, not a remote worker cluster
- Spec API `0.2` is a compatibility/versioning foundation, not a new language
  surface yet
- parallel model phases suppress token streaming to avoid interleaved terminal
  output

## Verification

Current test command:

```bash
pytest -q
```

Latest local run:

```text
345 passed
```

## Demo Path

```bash
python -m pip install -e ".[dev]"
pytest -q

forge new freelancer-crm -t web-app
cd freelancer-crm
$EDITOR .forge/spec.md

forge spec validate
forge spec compile --output .forge/compiled-spec.json
forge build -p ollama -v
forge serve --port 4123 --ui
```

For queued REST execution:

```bash
curl -s -X POST http://127.0.0.1:4123/api/builds \
  -H 'Content-Type: application/json' \
  -d '{"provider":"ollama","queue":true}'

forge worker --once
```

## Review Questions Worth Asking

- Are Spec API primitives expressive enough for the target application class?
- Are contract schemas strong enough to prevent backend/frontend drift?
- Should worker queue persistence remain SQLite-only or support pluggable queues?
- Which verification checks should be promoted from smoke tests to hard gates?
- What is the right boundary between deterministic scaffolds and model-owned
  implementation?
