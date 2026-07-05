import asyncio
import uuid
from datetime import datetime, timezone

from app.adapters.base import BaseATSAdapter


class WorkdayAdapter(BaseATSAdapter):
    provider = "workday"
    name = "Workday"

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.base_url = self.config.get("api_base_url", "https://api.workday.com/v1")
        self._connected = False

    async def health_check(self) -> dict:
        await asyncio.sleep(0.05)
        self._connected = True
        return {
            "provider": self.provider,
            "status": "connected",
            "version": "v36.2",
            "latency_ms": 45,
        }

    async def submit_job(self, job_data: dict) -> dict:
        await asyncio.sleep(0.15)
        job_id = f"wd-{uuid.uuid4().hex[:8]}"
        return {
            "provider_job_id": job_id,
            "status": "submitted",
            "requisition_id": f"REQ-{uuid.uuid4().hex[:6].upper()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_job_status(self, job_id: str) -> dict:
        await asyncio.sleep(0.05)
        return {"provider_job_id": job_id, "status": "published", "applicants": 23}

    async def search_candidates(self, query: dict) -> list[dict]:
        await asyncio.sleep(0.1)
        return [
            {
                "id": f"cand-{uuid.uuid4().hex[:6]}",
                "name": "John Doe",
                "email": "john.doe@email.com",
                "skills": query.get("skills", ["Python", "FastAPI"]),
                "match_score": 87.5,
            }
        ]

    async def get_candidate(self, candidate_id: str) -> dict:
        await asyncio.sleep(0.05)
        return {
            "id": candidate_id,
            "name": "Jane Smith",
            "email": "jane.smith@email.com",
            "phone": "+1-555-0123",
            "skills": ["Python", "AWS", "Docker", "PostgreSQL"],
            "experience_years": 6,
            "current_title": "Senior Backend Engineer",
            "education": [{"degree": "B.S. Computer Science", "university": "MIT"}],
        }
