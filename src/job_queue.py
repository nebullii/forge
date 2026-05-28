"""SQLite-backed local job queue for Forge workers."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class QueuedJob:
    id: str
    kind: str
    status: str = "queued"
    project_root: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
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
            "payload": self.payload,
            "build_id": self.build_id,
            "task_id": self.task_id,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class JobQueue:
    def __init__(self, forge_path: Path):
        self.forge_path = forge_path
        self.path = forge_path / "jobs.sqlite"
        self.forge_path.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def enqueue(self, kind: str, project_root: Path, payload: dict[str, Any] | None = None) -> QueuedJob:
        payload = dict(payload or {})
        job = QueuedJob(
            id=uuid.uuid4().hex[:10],
            kind=kind,
            project_root=str(project_root),
            payload=payload,
            task_id=str(payload.get("task_id") or ""),
        )
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO jobs (
                  id, kind, status, project_root, payload, build_id, task_id,
                  error, created_at, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id, job.kind, job.status, job.project_root,
                    json.dumps(job.payload, sort_keys=True), job.build_id,
                    job.task_id, job.error, job.created_at, job.started_at,
                    job.completed_at,
                ),
            )
        return job

    def list(self, project_root: Path | None = None) -> list[QueuedJob]:
        sql = "SELECT * FROM jobs"
        params: tuple[Any, ...] = ()
        if project_root is not None:
            sql += " WHERE project_root = ?"
            params = (str(project_root),)
        sql += " ORDER BY created_at DESC"
        with self._connect() as db:
            rows = db.execute(sql, params).fetchall()
        return [self._row_to_job(row) for row in rows]

    def claim_next(self, project_root: Path | None = None) -> QueuedJob | None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if project_root is None:
                row = db.execute(
                    "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT * FROM jobs WHERE status = 'queued' AND project_root = ? ORDER BY created_at LIMIT 1",
                    (str(project_root),),
                ).fetchone()
            if row is None:
                db.commit()
                return None
            started = datetime.now().isoformat()
            db.execute(
                "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ? AND status = 'queued'",
                (started, row["id"]),
            )
            db.commit()
        job = self._row_to_job(row)
        job.status = "running"
        job.started_at = started
        return job

    def complete(self, job_id: str, *, build_id: str = "") -> None:
        self._finish(job_id, "completed", build_id=build_id)

    def fail(self, job_id: str, error: str) -> None:
        self._finish(job_id, "failed", error=error)

    def _finish(self, job_id: str, status: str, *, build_id: str = "", error: str = "") -> None:
        with self._connect() as db:
            db.execute(
                """
                UPDATE jobs
                SET status = ?, build_id = COALESCE(NULLIF(?, ''), build_id),
                    error = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, build_id, error, datetime.now().isoformat(), job_id),
            )

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY,
                  kind TEXT NOT NULL,
                  status TEXT NOT NULL,
                  project_root TEXT NOT NULL,
                  payload TEXT NOT NULL,
                  build_id TEXT NOT NULL DEFAULT '',
                  task_id TEXT NOT NULL DEFAULT '',
                  error TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,
                  started_at TEXT NOT NULL DEFAULT '',
                  completed_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_root)")

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> QueuedJob:
        payload = json.loads(row["payload"] or "{}")
        return QueuedJob(
            id=row["id"],
            kind=row["kind"],
            status=row["status"],
            project_root=row["project_root"],
            payload=payload if isinstance(payload, dict) else {},
            build_id=row["build_id"],
            task_id=row["task_id"],
            error=row["error"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )
