from abc import ABC, abstractmethod
from typing import Any


class BaseATSAdapter(ABC):
    provider: str = "base"

    @abstractmethod
    async def submit_job(self, job_data: dict) -> dict:
        ...

    @abstractmethod
    async def get_job_status(self, job_id: str) -> dict:
        ...

    @abstractmethod
    async def search_candidates(self, query: dict) -> list[dict]:
        ...

    @abstractmethod
    async def get_candidate(self, candidate_id: str) -> dict:
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        ...
