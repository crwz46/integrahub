import asyncio
import uuid
from datetime import datetime, timezone

from app.adapters.base import BaseATSAdapter


class ICIMSAdapter(BaseATSAdapter):
    provider = "icims"
    name = "iCIMS"

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.base_url = self.config.get("api_base_url", "https://api.icims.com/v1")

    async def health_check(self) -> dict:
        await asyncio.sleep(0.05)
        return {
            "provider": self.provider,
            "status": "connected",
            "version": "v1",
            "customer_id": self.config.get("customer_id", "unknown"),
        }

    async def submit_job(self, job_data: dict) -> dict:
        await asyncio.sleep(0.12)
        job_id = f"ici-{uuid.uuid4().hex[:8]}"
        return {
            "provider_job_id": job_id,
            "status": "active",
            "career_site_url": f"https://career.acme.com/jobs/{job_id}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_job_status(self, job_id: str) -> dict:
        await asyncio.sleep(0.05)
        return {
            "provider_job_id": job_id,
            "status": "active",
            "applicants": 34,
            "interviews": 5,
        }

    async def search_candidates(self, query: dict) -> list[dict]:
        await asyncio.sleep(0.08)
        return [
            {
                "id": f"ici-cand-{uuid.uuid4().hex[:6]}",
                "name": "Diana Prince",
                "email": "diana@email.com",
                "skills": query.get("skills", ["Java", "Spring Boot"]),
                "match_score": 91.0,
            },
            {
                "id": f"ici-cand-{uuid.uuid4().hex[:6]}",
                "name": "Eve Adams",
                "email": "eve@email.com",
                "skills": query.get("skills", ["Python", "Django"]),
                "match_score": 76.5,
            },
        ]

    async def get_candidate(self, candidate_id: str) -> dict:
        await asyncio.sleep(0.05)
        return {
            "id": candidate_id,
            "name": "Diana Prince",
            "email": "diana@icims.com",
            "phone": "+1-555-0111",
            "skills": ["Java", "Spring Boot", "AWS", "Microservices"],
            "experience_years": 7,
            "current_title": "Backend Architect",
            "education": [{"degree": "M.S. Computer Science", "university": "Stanford"}],
        }
