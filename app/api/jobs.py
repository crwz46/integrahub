import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.adapters import AdapterRegistry
from app.config import settings
from app.core.queue import AsyncJobQueue
from app.models import Job, JobCreate, JobListResponse, JobStatus

router = APIRouter(prefix="/jobs", tags=["Jobs"])

queue = AsyncJobQueue()

_integrations_path = Path(settings.data_path) / "integrations"


def _get_job_folder() -> Path:
    p = Path(settings.data_path) / "jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


async def _process_job(job: dict):
    job["status"] = "processing"
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_job(job)

    try:
        integration_path = _integrations_path / f"{job['integration_id']}.json"
        if not integration_path.exists():
            raise ValueError("Integration not found")
        with open(integration_path) as f:
            integration = json.load(f)

        adapter = AdapterRegistry.get(integration["provider"], integration.get("config"))
        result = await adapter.submit_job(job["payload"])

        job["status"] = "completed"
        job["result"] = result
        job["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_job(job)
        return result
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_job(job)
        return None


def _save_job(job: dict):
    folder = _get_job_folder()
    with open(folder / f"{job['id']}.json", "w") as f:
        json.dump(job, f)


def _load_job(job_id: str) -> dict | None:
    path = _get_job_folder() / f"{job_id}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def _load_all_jobs(status: Optional[str] = None, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
    jobs = []
    for p in _get_job_folder().glob("*.json"):
        with open(p) as f:
            j = json.load(f)
            if status and j.get("status") != status:
                continue
            jobs.append(j)
    jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    total = len(jobs)
    start = (page - 1) * page_size
    return jobs[start:start + page_size], total


async def _process_worker():
    while True:
        try:
            job = queue.dequeue()
            if job:
                jtype = job.get("type", "")
                if jtype == "ats_job":
                    await _process_job(job)
                    queue.complete(job["id"], job.get("result"))
                else:
                    queue.fail(job["id"], f"Unknown job type: {jtype}")
            await asyncio.sleep(settings.queue_poll_interval_seconds)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(1)


_worker_task: Optional[asyncio.Task] = None


def start_worker():
    global _worker_task
    if _worker_task is None:
        _worker_task = asyncio.create_task(_process_worker())


def stop_worker():
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        _worker_task = None


@router.post("", response_model=Job, status_code=201)
async def create_job(data: JobCreate):
    integration_path = _integrations_path / f"{data.integration_id}.json"
    if not integration_path.exists():
        raise HTTPException(404, "Integration not found")

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    job = {
        "id": job_id,
        "integration_id": data.integration_id,
        "status": JobStatus.pending.value,
        "payload": data.payload,
        "result": None,
        "error": None,
        "attempts": 0,
        "priority": data.priority,
        "webhook_url": data.webhook_url,
        "created_at": now,
        "updated_at": now,
    }
    _save_job(job)
    queue.enqueue("ats_job", {"job_id": job_id, "integration_id": data.integration_id}, priority=data.priority)
    return job


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    jobs, total = _load_all_jobs(status, page, page_size)
    return {"jobs": jobs, "total": total, "page": page, "page_size": page_size}


@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str):
    job = _load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/{job_id}/retry", response_model=Job)
async def retry_job(job_id: str):
    job = _load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "failed":
        raise HTTPException(400, "Only failed jobs can be retried")
    job["status"] = JobStatus.pending.value
    job["error"] = None
    job["attempts"] += 1
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_job(job)
    queue.enqueue("ats_job", {"job_id": job_id, "integration_id": job["integration_id"]}, priority=job.get("priority", 0))
    return job


@router.get("/stats/queue")
async def queue_stats():
    return queue.stats()
