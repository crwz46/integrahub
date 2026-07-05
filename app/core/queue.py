import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.config import settings


class AsyncJobQueue:
    def __init__(self, data_path: str | None = None):
        self.base_path = Path(data_path or settings.data_path) / "queue"
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._pending_path = self.base_path / "pending"
        self._processing_path = self.base_path / "processing"
        self._failed_path = self.base_path / "failed"
        self._completed_path = self.base_path / "completed"
        for p in [self._pending_path, self._processing_path, self._failed_path, self._completed_path]:
            p.mkdir(exist_ok=True)
        self._handlers: dict[str, Callable] = {}
        self._worker_task: asyncio.Task | None = None

    def register_handler(self, job_type: str, handler: Callable):
        self._handlers[job_type] = handler

    def enqueue(self, job_type: str, payload: dict, priority: int = 0) -> str:
        job_id = str(uuid.uuid4())
        job = {
            "id": job_id,
            "type": job_type,
            "payload": payload,
            "priority": priority,
            "attempts": 0,
            "max_attempts": settings.queue_max_retries,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }
        with open(self._pending_path / f"{job_id}.json", "w") as f:
            json.dump(job, f)
        return job_id

    def dequeue(self) -> dict | None:
        items = sorted(
            self._pending_path.iterdir(),
            key=lambda p: self._get_priority(p),
        )
        for item in items:
            if item.suffix != ".json":
                continue
            dest = self._processing_path / item.name
            try:
                item.rename(dest)
                with open(dest) as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
        return None

    def _get_priority(self, path: Path) -> tuple:
        try:
            with open(path) as f:
                job = json.load(f)
                return (-job.get("priority", 0), job.get("created_at", ""))
        except (OSError, json.JSONDecodeError):
            return (0, "")

    def complete(self, job_id: str, result: dict | None = None):
        src = self._processing_path / f"{job_id}.json"
        dst = self._completed_path / f"{job_id}.json"
        if src.exists():
            with open(src) as f:
                job = json.load(f)
            job["status"] = "completed"
            job["result"] = result
            job["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(dst, "w") as f:
                json.dump(job, f)
            src.unlink(missing_ok=True)

    def fail(self, job_id: str, error: str):
        src = self._processing_path / f"{job_id}.json"
        dst = self._failed_path / f"{job_id}.json"
        if src.exists():
            with open(src) as f:
                job = json.load(f)
            job["status"] = "failed"
            job["error"] = error
            job["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(dst, "w") as f:
                json.dump(job, f)
            src.unlink(missing_ok=True)

    def retry(self, job_id: str):
        for folder in [self._failed_path, self._processing_path]:
            src = folder / f"{job_id}.json"
            if src.exists():
                with open(src) as f:
                    job = json.load(f)
                job["attempts"] += 1
                job["updated_at"] = datetime.now(timezone.utc).isoformat()
                if job["attempts"] >= job.get("max_attempts", 3):
                    job["status"] = "failed"
                    with open(self._failed_path / f"{job_id}.json", "w") as f:
                        json.dump(job, f)
                    if src != self._failed_path / f"{job_id}.json":
                        src.unlink(missing_ok=True)
                    return
                with open(self._pending_path / f"{job_id}.json", "w") as f:
                    json.dump(job, f)
                src.unlink(missing_ok=True)
                return

    def stats(self) -> dict:
        return {
            "pending": len(list(self._pending_path.glob("*.json"))),
            "processing": len(list(self._processing_path.glob("*.json"))),
            "completed": len(list(self._completed_path.glob("*.json"))),
            "failed": len(list(self._failed_path.glob("*.json"))),
        }

    def list_jobs(self, status: str | None = None, limit: int = 50) -> list[dict]:
        folders = {
            "pending": self._pending_path,
            "processing": self._processing_path,
            "completed": self._completed_path,
            "failed": self._failed_path,
        }
        if status and status in folders:
            paths = list(folders[status].glob("*.json"))
        else:
            paths = []
            for f in folders.values():
                paths.extend(f.glob("*.json"))
        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        result = []
        for p in paths[:limit]:
            try:
                with open(p) as f:
                    result.append(json.load(f))
            except (OSError, json.JSONDecodeError):
                continue
        return result
