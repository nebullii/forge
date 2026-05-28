"""Local REST control plane for Forge."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .agents.registry import agent_card, list_capabilities
from .job_queue import JobQueue, QueuedJob
from .providers.base import ProviderConfig
from .router import ModelRouter
from .specapi import compile_task_graph, parse_spec_file, parse_spec_text


@dataclass
class ControlJob:
    id: str
    kind: str
    status: str = "queued"
    project_root: str = ""
    build_id: str = ""
    task_id: str = ""
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "project_root": self.project_root,
            "build_id": self.build_id,
            "task_id": self.task_id,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


_JOBS: dict[str, ControlJob] = {}
_JOBS_LOCK = threading.Lock()


def run_control_plane(host: str = "127.0.0.1", port: int = 4123, project_root: Path | None = None, ui: bool = False) -> None:
    """Run Forge's local JSON API server."""
    root = project_root or Path.cwd()
    handler = _make_handler(root)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Forge API listening on http://{host}:{port}")
    if ui:
        print(f"Dashboard available at http://{host}:{port}/dashboard")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
    finally:
        server.server_close()


def _make_handler(project_root: Path):
    class ForgeRequestHandler(BaseHTTPRequestHandler):
        server_version = "ForgeControlPlane/0.1"

        def do_GET(self):  # noqa: N802
            self._handle("GET")

        def do_POST(self):  # noqa: N802
            self._handle("POST")

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _handle(self, method: str) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)
            try:
                if method == "GET" and path in {"/", "/dashboard"}:
                    self._html(200, _dashboard_html())
                elif method == "GET" and path == "/.well-known/agent.json":
                    self._json(200, agent_card())
                elif method == "GET" and path == "/api/agents":
                    self._json(200, {"agents": list_capabilities()})
                elif method == "GET" and path == "/api/health":
                    self._json(200, {"ok": True, "service": "forge-control-plane"})
                elif method == "POST" and path == "/api/spec/validate":
                    payload = self._payload()
                    doc = _document_from_payload(payload, project_root)
                    self._json(200, doc.to_dict())
                elif method == "POST" and path == "/api/spec/compile":
                    payload = self._payload()
                    doc = _document_from_payload(payload, project_root)
                    graph = compile_task_graph(doc)
                    self._json(200, {"spec": doc.to_dict(), "task_graph": graph.to_dict()})
                elif method == "GET" and path == "/api/tasks":
                    self._json(200, _task_graph_payload(project_root))
                elif method == "GET" and path.startswith("/api/tasks/"):
                    task_id = path.split("/")[-1]
                    task = _task_payload(project_root, task_id)
                    self._json(200 if task else 404, task or {"error": f"task not found: {task_id}"})
                elif method == "GET" and path == "/api/contracts":
                    self._json(200, _read_json(project_root / ".forge" / "contracts.json"))
                elif method == "GET" and path == "/api/artifacts":
                    self._json(200, {"artifacts": _read_jsonl(project_root / ".forge" / "artifacts.jsonl")})
                elif method == "GET" and path == "/api/audit":
                    self._json(200, {"events": _audit_events(project_root)})
                elif method == "GET" and path == "/api/models":
                    self._json(200, _models_payload())
                elif method == "GET" and path == "/api/models/health":
                    self._json(200, _models_health())
                elif method == "POST" and path == "/api/models/route":
                    role = str(self._payload().get("role") or "coder")
                    self._json(200, _route_model(role))
                elif method == "POST" and path in {"/api/models/chat", "/api/models/generate"}:
                    self._json(200, _model_generate(self._payload(), chat=(path.endswith("/chat"))))
                elif method == "POST" and path == "/api/agents/validate-output":
                    from .agents.contracts import validate_agent_output
                    payload = self._payload()
                    output = validate_agent_output(payload.get("output") or {}, role=str(payload.get("role") or ""))
                    self._json(200, {"valid": True, "output": output.to_dict()})
                elif method == "POST" and path == "/api/verify":
                    self._json(200, _verification_summary(project_root))
                elif method == "GET" and path == "/api/contracts/openapi":
                    self._json(200, _openapi_payload(project_root))
                elif method == "GET" and path == "/api/builds":
                    self._json(200, {
                        "state": _build_state(project_root),
                        "jobs": _jobs_for_project(project_root),
                    })
                elif method == "GET" and path == "/api/jobs":
                    self._json(200, {"jobs": _queued_jobs_for_project(project_root)})
                elif method == "GET" and path.startswith("/api/builds/") and path.endswith("/events/stream"):
                    parts = path.split("/")
                    build_id = parts[-3] if len(parts) >= 3 else ""
                    self._sse(_events_payload(project_root, build_id=build_id), once=_truthy(query.get("once", [""])[0]))
                elif method == "GET" and path.startswith("/api/builds/") and path.endswith("/events"):
                    parts = path.split("/")
                    build_id = parts[-2] if len(parts) >= 2 else ""
                    self._json(200, _events_payload(project_root, build_id=build_id))
                elif method == "GET" and path.startswith("/api/builds/"):
                    build_id = path.split("/")[-1]
                    self._json(200, {
                        "state": _build_state(project_root, build_id=build_id),
                        "jobs": [
                            job for job in _jobs_for_project(project_root)
                            if job.get("build_id") in {"", build_id} or job.get("id") == build_id
                        ],
                    })
                elif method == "GET" and path == "/api/events/stream":
                    self._sse(_events_payload(project_root), once=_truthy(query.get("once", [""])[0]))
                elif method == "GET" and path.startswith("/api/events"):
                    self._json(200, _events_payload(project_root))
                elif method == "POST" and path == "/api/builds":
                    job = start_build_job(project_root, self._payload())
                    self._json(202, {"status": "accepted", "job": job.to_dict()})
                elif method == "POST" and path.startswith("/api/tasks/") and path.endswith("/run"):
                    task_id = path.split("/")[-2]
                    payload = self._payload()
                    payload["task_id"] = task_id
                    job = start_task_job(project_root, payload)
                    self._json(202, {"status": "accepted", "job": job.to_dict()})
                elif method == "POST" and path.startswith("/api/tasks/") and path.endswith("/retry"):
                    task_id = path.split("/")[-2]
                    payload = self._payload()
                    payload["task_id"] = task_id
                    payload["retry"] = True
                    job = start_task_job(project_root, payload)
                    self._json(202, {"status": "accepted", "job": job.to_dict()})
                else:
                    self._json(404, {"error": f"unknown endpoint {method} {path}", "query": query})
            except FileNotFoundError as exc:
                self._json(404, {"error": str(exc)})
            except Exception as exc:
                self._json(500, {"error": str(exc)})

        def _payload(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            if not raw.strip():
                return {}
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            return data

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _html(self, status: int, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _sse(self, payload: dict[str, Any], *, once: bool = False) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            while True:
                self.wfile.write(_sse_event("forge.events", payload))
                self.wfile.flush()
                if once:
                    return
                time.sleep(1)

    return ForgeRequestHandler


def start_build_job(project_root: Path, payload: dict[str, Any] | None = None) -> ControlJob:
    """Start a background full-build job using the real orchestrator."""
    payload = payload or {}
    if payload.get("queue") or payload.get("distributed"):
        return _enqueue_control_job(project_root, "build", payload)
    job = ControlJob(
        id=uuid.uuid4().hex[:10],
        kind="build",
        project_root=str(project_root),
    )
    _remember_job(job)
    _log_control_event(project_root, "job_queued", job=job.to_dict())
    thread = threading.Thread(
        target=_run_job,
        args=(job, _run_build_worker, project_root, payload),
        daemon=True,
    )
    thread.start()
    return job


def start_task_job(project_root: Path, payload: dict[str, Any] | None = None) -> ControlJob:
    """Start a background single-task job using the real orchestrator task runner."""
    payload = payload or {}
    task_id = str(payload.get("task_id") or "")
    if payload.get("queue") or payload.get("distributed"):
        return _enqueue_control_job(project_root, "task", payload)
    job = ControlJob(
        id=uuid.uuid4().hex[:10],
        kind="task",
        project_root=str(project_root),
        task_id=task_id,
    )
    _remember_job(job)
    _log_control_event(project_root, "job_queued", job=job.to_dict())
    thread = threading.Thread(
        target=_run_job,
        args=(job, _run_task_worker, project_root, payload),
        daemon=True,
    )
    thread.start()
    return job


def _enqueue_control_job(project_root: Path, kind: str, payload: dict[str, Any]) -> ControlJob:
    queued = JobQueue(project_root / ".forge").enqueue(kind, project_root, payload)
    job = _control_job_from_queued(queued)
    _remember_job(job)
    _log_control_event(project_root, "job_queued", job=job.to_dict(), durable=True)
    return job


def _control_job_from_queued(job: QueuedJob) -> ControlJob:
    return ControlJob(
        id=job.id,
        kind=job.kind,
        status=job.status,
        project_root=job.project_root,
        build_id=job.build_id,
        task_id=job.task_id,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def run_worker(project_root: Path | None = None, *, once: bool = False, poll_interval: float = 1.0) -> None:
    """Run queued Forge jobs from the SQLite-backed local queue."""
    root = project_root or Path.cwd()
    queue = JobQueue(root / ".forge")
    print(f"Forge worker watching {queue.path}")
    while True:
        job = queue.claim_next(root)
        if job is None:
            if once:
                print("No queued jobs.")
                return
            time.sleep(poll_interval)
            continue
        _log_control_event(root, "worker_job_started", job=job.to_dict())
        try:
            if job.kind == "build":
                build_id = _run_build_worker(root, job.payload)
            elif job.kind == "task":
                build_id = _run_task_worker(root, job.payload)
            else:
                raise ValueError(f"unknown queued job kind: {job.kind}")
            queue.complete(job.id, build_id=build_id)
            _log_control_event(root, "worker_job_completed", job_id=job.id, build_id=build_id)
            print(f"Completed {job.kind} job {job.id}")
        except Exception as exc:
            queue.fail(job.id, str(exc))
            _log_control_event(root, "worker_job_failed", job_id=job.id, error=str(exc))
            print(f"Failed {job.kind} job {job.id}: {exc}")
        if once:
            return


def _remember_job(job: ControlJob) -> None:
    with _JOBS_LOCK:
        _JOBS[job.id] = job
        if len(_JOBS) > 100:
            for key in sorted(_JOBS, key=lambda item: _JOBS[item].created_at)[:-100]:
                _JOBS.pop(key, None)


def _run_job(job: ControlJob, fn, project_root: Path, payload: dict[str, Any]) -> None:
    job.status = "running"
    job.started_at = datetime.now().isoformat()
    _log_control_event(project_root, "job_started", job=job.to_dict())
    try:
        build_id = fn(project_root, payload)
        if build_id:
            job.build_id = build_id
        job.status = "completed"
        job.completed_at = datetime.now().isoformat()
        _log_control_event(project_root, "job_completed", job=job.to_dict())
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.completed_at = datetime.now().isoformat()
        _log_control_event(project_root, "job_failed", job=job.to_dict(), error=str(exc))
    finally:
        if not job.completed_at:
            job.completed_at = datetime.now().isoformat()


def _run_build_worker(project_root: Path, payload: dict[str, Any]) -> str:
    orchestrator = _make_orchestrator(project_root, payload)
    orchestrator.run(feature=payload.get("feature"))
    return orchestrator.state.build_id


def _run_task_worker(project_root: Path, payload: dict[str, Any]) -> str:
    task_id = str(payload.get("task_id") or "")
    if not task_id:
        raise ValueError("task_id is required")

    orchestrator = _make_orchestrator(project_root, payload)
    spec = orchestrator._read_forge_file("spec.md")
    rules = orchestrator._read_forge_file("rules.md")
    if not spec:
        raise ValueError(".forge/spec.md is empty or missing")

    if not orchestrator.state.tasks:
        orchestrator._init_state(spec)
        orchestrator._phase_plan(spec, rules, payload.get("feature"))

    task = orchestrator._task_by_id(task_id)
    if task is None:
        raise ValueError(f"unknown task: {task_id}")
    if payload.get("retry") and task.status == "failed":
        task.status = "pending"
        task.error = ""
        orchestrator._save_state()

    _ensure_task_dependencies_complete(orchestrator, task_id)
    orchestrator._run_single_task(task_id, spec, rules)
    orchestrator.registry.save(orchestrator.forge_path / "contracts.json")
    return orchestrator.state.build_id


def _make_orchestrator(project_root: Path, payload: dict[str, Any]):
    from .config import load_config
    from .orchestrator import BuildOrchestrator
    from .router import _provider_config_from_dict

    forge_path = project_root / ".forge"
    if not forge_path.exists():
        raise FileNotFoundError(f"No .forge directory found at {forge_path}")

    config = payload.get("config") if isinstance(payload.get("config"), dict) else load_config()
    config = config or {}
    provider_ref = payload.get("provider")
    provider_data = _select_provider_data(config, str(provider_ref or ""))
    provider_config = _provider_config_from_dict(provider_data)
    if payload.get("model"):
        provider_config.model = str(payload["model"])

    return BuildOrchestrator(
        provider_config=provider_config,
        forge_path=forge_path,
        review=not bool(payload.get("no_review", False)),
        verbose=bool(payload.get("verbose", False)),
        approval_mode=payload.get("approval_mode"),
        provider_scope=str(provider_ref or "") or None,
        config_dict=config,
    )


def _select_provider_data(config: dict[str, Any], provider_ref: str = "") -> dict[str, Any]:
    providers = [item for item in config.get("providers", []) if isinstance(item, dict)]
    if not providers:
        raise ValueError("No providers configured")

    if provider_ref:
        ref = provider_ref.lower()
        for provider in providers:
            name = str(provider.get("name", "")).lower()
            if name == ref:
                return provider
            profiles = provider.get("profiles", {})
            if isinstance(profiles, dict):
                for profile_name, profile in profiles.items():
                    refs = {
                        profile_name.lower(),
                        f"{name}:{profile_name}".lower(),
                        f"{name}/{profile_name}".lower(),
                    }
                    if ref in refs:
                        merged = dict(provider)
                        merged.update(profile or {})
                        merged.pop("profiles", None)
                        merged["profile"] = profile_name
                        return merged
        raise ValueError(f"Provider '{provider_ref}' not found in config")

    for provider in providers:
        if provider.get("base_url") or str(provider.get("api_key") or "").strip():
            return provider
    raise ValueError("No provider has credentials or base_url configured")


def _ensure_task_dependencies_complete(orchestrator, task_id: str) -> None:
    from .scheduler import build_dependency_graph

    graph = build_dependency_graph(orchestrator.state.tasks)
    deps = set()
    for node in graph:
        if node.task_id == task_id:
            deps = node.depends_on
            break
    incomplete = [
        dep for dep in deps
        if (orchestrator._task_by_id(dep) is None or orchestrator._task_by_id(dep).status != "completed")
    ]
    if incomplete:
        raise RuntimeError(f"Task '{task_id}' is blocked by incomplete dependencies: {', '.join(sorted(incomplete))}")


def _jobs_for_project(project_root: Path) -> list[dict[str, Any]]:
    root = str(project_root)
    with _JOBS_LOCK:
        memory_jobs = [
            job.to_dict()
            for job in _JOBS.values()
            if job.project_root == root
        ]
    queued = _queued_jobs_for_project(project_root)
    seen = {job["id"] for job in memory_jobs}
    return memory_jobs + [job for job in queued if job["id"] not in seen]


def _queued_jobs_for_project(project_root: Path) -> list[dict[str, Any]]:
    queue = JobQueue(project_root / ".forge")
    return [job.to_dict() for job in queue.list(project_root)]


def _events_payload(project_root: Path, build_id: str = "") -> dict[str, Any]:
    """Return recent build events from jobs, build state, and audit logs."""
    events: list[dict[str, Any]] = []
    for job in _jobs_for_project(project_root):
        if build_id and job.get("build_id") not in {"", build_id} and job.get("id") != build_id:
            continue
        events.append({
            "type": "job",
            "timestamp": job.get("created_at", ""),
            "job": job,
        })

    state = _build_state(project_root, build_id=build_id)
    if state.get("status") != "not_started":
        events.append({
            "type": "build_state",
            "timestamp": state.get("started_at", ""),
            "state": state,
        })

    for item in _audit_events(project_root):
        if build_id and str(item.get("build_id", "")) not in {"", build_id}:
            continue
        events.append({
            "type": item.get("event", "audit"),
            "timestamp": item.get("timestamp", ""),
            "audit": item,
        })

    events.sort(key=lambda item: item.get("timestamp", ""))
    return {"events": events[-200:]}


def _audit_events(project_root: Path) -> list[dict[str, Any]]:
    forge_path = project_root / ".forge"
    events: list[dict[str, Any]] = []
    for name in ("audit.jsonl", "build_audit.jsonl", "control_audit.jsonl"):
        events.extend(_read_jsonl(forge_path / name))
    return events


def _log_control_event(project_root: Path, event: str, **data: Any) -> None:
    forge_path = project_root / ".forge"
    forge_path.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event,
        **data,
    }
    with open(forge_path / "control_audit.jsonl", "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def _sse_event(event: str, data: dict[str, Any]) -> bytes:
    encoded = json.dumps(data, sort_keys=True)
    return f"event: {event}\ndata: {encoded}\n\n".encode("utf-8")


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Forge Dashboard</title>
    <style>
      body { margin: 0; font: 14px system-ui, sans-serif; background: #0c0c0e; color: #f4f4f5; }
      header { padding: 18px 24px; border-bottom: 1px solid #27272a; display: flex; justify-content: space-between; align-items: center; }
      main { padding: 24px; display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
      section { border: 1px solid #27272a; border-radius: 8px; padding: 16px; background: #111114; }
      h1 { margin: 0; font-size: 18px; }
      h2 { margin: 0 0 12px; font-size: 14px; color: #a1a1aa; }
      pre { white-space: pre-wrap; word-break: break-word; margin: 0; font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; color: #d4d4d8; }
      button { background: #60a5fa; color: #020617; border: 0; border-radius: 6px; padding: 7px 12px; font-weight: 600; cursor: pointer; }
      .muted { color: #71717a; }
    </style>
  </head>
  <body>
    <header>
      <div>
        <h1>Forge Dashboard</h1>
        <div class="muted">Local build state, tasks, contracts, jobs, and events</div>
      </div>
      <button id="refresh">Refresh</button>
    </header>
    <main>
      <section><h2>Builds</h2><pre id="builds">Loading...</pre></section>
      <section><h2>Tasks</h2><pre id="tasks">Loading...</pre></section>
      <section><h2>Contracts</h2><pre id="contracts">Loading...</pre></section>
      <section><h2>Jobs</h2><pre id="jobs">Loading...</pre></section>
      <section><h2>Agents</h2><pre id="agents">Loading...</pre></section>
      <section><h2>Events</h2><pre id="events">Loading...</pre></section>
    </main>
    <script>
      const endpoints = {
        builds: '/api/builds',
        tasks: '/api/tasks',
        contracts: '/api/contracts',
        jobs: '/api/jobs',
        agents: '/api/agents',
        events: '/api/events'
      };
      async function load() {
        for (const [id, url] of Object.entries(endpoints)) {
          const el = document.getElementById(id);
          try {
            const res = await fetch(url);
            el.textContent = JSON.stringify(await res.json(), null, 2);
          } catch (err) {
            el.textContent = String(err);
          }
        }
      }
      document.getElementById('refresh').addEventListener('click', load);
      load();
    </script>
  </body>
</html>
"""


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _document_from_payload(payload: dict[str, Any], project_root: Path):
    if "text" in payload:
        return parse_spec_text(str(payload["text"]))
    path = Path(payload.get("path") or project_root / ".forge" / "spec.md")
    if not path.is_absolute():
        path = project_root / path
    return parse_spec_file(path)


def _document_from_project(project_root: Path):
    return parse_spec_file(project_root / ".forge" / "spec.md")


def _task_graph_payload(project_root: Path) -> dict[str, Any]:
    cached = project_root / ".forge" / "task-graph.json"
    if cached.exists():
        return _read_json(cached)
    doc = _document_from_project(project_root)
    return {"spec": doc.to_dict(), "task_graph": compile_task_graph(doc).to_dict()}


def _task_payload(project_root: Path, task_id: str) -> dict[str, Any] | None:
    payload = _task_graph_payload(project_root)
    graph = payload.get("task_graph", payload)
    for task in graph.get("tasks", []):
        if task.get("id") == task_id:
            return task

    state = _build_state(project_root)
    for task in state.get("tasks", []) if isinstance(state, dict) else []:
        if task.get("id") == task_id:
            return task
    return None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return data if isinstance(data, dict) else {"data": data}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"raw": line})
    return rows


def _load_config() -> dict[str, Any]:
    try:
        from .config import load_config
        return load_config() or {}
    except Exception:
        return {}


def _models_payload() -> dict[str, Any]:
    config = _load_config()
    return {"providers": config.get("providers", []), "model_routing": config.get("model_routing", {})}


def _models_health() -> dict[str, Any]:
    config = _load_config()
    providers = []
    for provider in config.get("providers", []):
        if not isinstance(provider, dict):
            continue
        item = {"name": provider.get("name"), "model": provider.get("model"), "ok": True}
        if provider.get("name") == "ollama":
            item["base_url"] = provider.get("base_url") or "http://localhost:11434"
            item["ok"] = bool(_ollama_tags(item["base_url"]))
        providers.append(item)
    return {"providers": providers}


def _route_model(role: str) -> dict[str, Any]:
    config = _load_config()
    providers = config.get("providers") or [{"name": "ollama", "base_url": "http://localhost:11434", "model": "llama3.1"}]
    first = providers[0]
    default = ProviderConfig(
        name=first.get("name", "ollama"),
        api_key=first.get("api_key", ""),
        base_url=first.get("base_url", ""),
        model=first.get("model", "llama3.1"),
    )
    router = ModelRouter(config=config, default_provider=default)
    chain = router.route_chain(role)
    return {
        "role": role,
        "candidates": [
            {
                "provider": item.provider_config.name,
                "profile": item.provider_config.profile,
                "model": item.provider_config.model,
                "reason": item.reason,
                "rank": item.rank,
            }
            for item in chain
        ],
    }


def _model_generate(payload: dict[str, Any], *, chat: bool) -> dict[str, Any]:
    """Invoke the routed model gateway.

    The endpoint intentionally accepts typed task context but only forwards the
    message content to the provider. Artifacts/contracts remain Forge-managed.
    """
    role = str(payload.get("role") or "coder")
    route = _route_model(role)
    candidates = route.get("candidates") or []
    if not candidates:
        raise ValueError(f"no model candidates for role {role}")

    selected = candidates[0]
    config = _load_config()
    provider_cfg = _provider_config_for(selected, config)
    from .providers import create_provider
    provider = create_provider(provider_cfg)

    if chat:
        messages = payload.get("messages")
        if not isinstance(messages, list):
            prompt = str(payload.get("prompt") or "")
            messages = [{"role": "user", "content": prompt}]
    else:
        prompt = str(payload.get("prompt") or payload.get("input") or "")
        messages = [{"role": "user", "content": prompt}]

    response = provider.chat(
        messages,
        system=str(payload.get("system") or ""),
        json_mode=bool(payload.get("json_mode", False)),
    )
    usage = provider.get_last_usage()
    return {
        "role": role,
        "provider": provider_cfg.name,
        "model": provider_cfg.model,
        "response": response,
        "usage": usage or {},
    }


def _provider_config_for(selected: dict[str, Any], config: dict[str, Any]) -> ProviderConfig:
    provider_name = selected.get("provider") or "ollama"
    profile = selected.get("profile") or ""
    model = selected.get("model") or "llama3.1"
    for provider in config.get("providers", []):
        if not isinstance(provider, dict) or provider.get("name") != provider_name:
            continue
        base = dict(provider)
        profiles = base.get("profiles")
        if profile and isinstance(profiles, dict):
            profile_key = str(profile).split(":")[-1]
            if profile_key in profiles:
                base.update(profiles[profile_key] or {})
        return ProviderConfig(
            name=provider_name,
            api_key=base.get("api_key", ""),
            base_url=base.get("base_url", ""),
            model=base.get("model", model),
            profile=str(profile),
        )
    return ProviderConfig(name=provider_name, base_url="http://localhost:11434", model=model, profile=str(profile))


def _ollama_tags(base_url: str) -> list[str]:
    try:
        import requests
        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=1.5)
        response.raise_for_status()
        return [item.get("model") or item.get("name") for item in response.json().get("models", []) if item.get("model") or item.get("name")]
    except Exception:
        return []


def _verification_summary(project_root: Path) -> dict[str, Any]:
    path = project_root / ".forge" / "verification.json"
    return {"verification": _read_json(path), "source": str(path)}


def _openapi_payload(project_root: Path) -> dict[str, Any]:
    contracts = _read_json(project_root / ".forge" / "contracts.json")
    if "openapi" in contracts:
        return contracts
    return {"contracts": contracts}


def _build_state(project_root: Path, build_id: str = "") -> dict[str, Any]:
    path = project_root / ".forge" / "build-state.yaml"
    if not path.exists():
        return {"status": "not_started", "build_id": build_id}
    import yaml
    data = yaml.safe_load(path.read_text()) or {}
    if build_id and str(data.get("build_id", "")) not in {"", build_id}:
        return {"status": "not_found", "build_id": build_id}
    return data
