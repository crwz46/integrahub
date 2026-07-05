import asyncio
import uuid
from datetime import datetime, timezone

from app.adapters.base import BaseATSAdapter


class LeverAdapter(BaseATSAdapter):
    provider = "lever"
    name = "Lever"

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.base_url = self.config.get("api_base_url", "https://api.lever.co/v1")

    async def health_check(self) -> dict:
        await asyncio.sleep(0.05)
        return {
            "provider": self.provider,
            "status": "connected",
            "version": "v1",
            "sandbox": self.config.get("sandbox", False),
        }

    async def submit_job(self, job_data: dict) -> dict:
        await asyncio.sleep(0.1)
        job_id = f"lev-{uuid.uuid4().hex[:8]}"
        return {
            "provider_job_id": job_id,
            "status": "published",
            "posting_url": f"https://jobs.lever.co/acme/{job_id}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_job_status(self, job_id: str) -> dict:
        await asyncio.sleep(0.05)
        return {
            "provider_job_id": job_id,
            "status": "published",
            "applicants": 12,
            "stage": "interview",
        }

    async def search_candidates(self, query: dict) -> list[dict]:
        await asyncio.sleep(0.08)
        return [
            {
                "id": f"lev-cand-{uuid.uuid4().hex[:6]}",
                "name": "Charlie Brown",
                "email": "charlie@email.com",
                "skills": query.get("skills", ["JavaScript", "React"]),
                "match_score": 85.0,
            }
        ]

    async def get_candidate(self, candidate_id: str) -> dict:
        await asyncio.sleep(0.05)
        return {
            "id": candidate_id,
            "name": "Charlie Brown",
            "email": "charlie@lever.co",
            "phone": "+1-555-0789",
            "skills": ["JavaScript", "React", "Node.js", "TypeScript"],
            "experience_years": 5,
            "current_title": "Frontend Lead",
            "applications": [{"job": "Senior Frontend Engineer", "status": "interview"}],
        }
