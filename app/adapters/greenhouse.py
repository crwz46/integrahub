import asyncio
import uuid
from datetime import datetime, timezone

from app.adapters.base import BaseATSAdapter


class GreenhouseAdapter(BaseATSAdapter):
    provider = "greenhouse"
    name = "Greenhouse"

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.base_url = self.config.get("api_base_url", "https://api.greenhouse.io/v1")
        self._rate_limit_remaining = 100

    async def health_check(self) -> dict:
        await asyncio.sleep(0.05)
        return {
            "provider": self.provider,
            "status": "connected",
            "version": "v1",
            "rate_limit_remaining": self._rate_limit_remaining,
        }

    async def submit_job(self, job_data: dict) -> dict:
        await asyncio.sleep(0.12)
        self._rate_limit_remaining -= 1
        job_id = f"gh-{uuid.uuid4().hex[:8]}"
        return {
            "provider_job_id": job_id,
            "status": "live",
            "board_url": f"https://boards.greenhouse.io/jobs/{job_id}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_job_status(self, job_id: str) -> dict:
        await asyncio.sleep(0.05)
        return {
            "provider_job_id": job_id,
            "status": "live",
            "applicants": 45,
            "interviews_scheduled": 8,
        }

    async def search_candidates(self, query: dict) -> list[dict]:
        await asyncio.sleep(0.08)
        return [
            {
                "id": f"gh-cand-{uuid.uuid4().hex[:6]}",
                "name": "Alice Johnson",
                "email": "alice.j@email.com",
                "skills": query.get("skills", ["Go", "PostgreSQL"]),
                "match_score": 92.0,
            },
            {
                "id": f"gh-cand-{uuid.uuid4().hex[:6]}",
                "name": "Bob Williams",
                "email": "bob.w@email.com",
                "skills": query.get("skills", ["Python", "Django"]),
                "match_score": 78.3,
            },
        ]

    async def get_candidate(self, candidate_id: str) -> dict:
        await asyncio.sleep(0.05)
        return {
            "id": candidate_id,
            "name": "Alice Johnson",
            "email": "alice.j@greenhouse.io",
            "phone": "+1-555-0456",
            "skills": ["Go", "PostgreSQL", "Redis", "Kubernetes"],
            "experience_years": 8,
            "current_title": "Staff Software Engineer",
            "applications": [{"job": "Senior Backend Engineer", "status": "interview"}],
        }
