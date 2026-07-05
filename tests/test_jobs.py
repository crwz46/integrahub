import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def integration_id(client: AsyncClient) -> str:
    resp = await client.post(
        "/integrations",
        json={
            "name": "Job Test Integration",
            "provider": "workday",
            "api_base_url": "https://api.workday.com/v1",
        },
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_job(client: AsyncClient, integration_id: str):
    resp = await client.post(
        "/jobs",
        json={
            "integration_id": integration_id,
            "payload": {"title": "Senior Engineer", "location": "Remote"},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["integration_id"] == integration_id
    assert data["payload"]["title"] == "Senior Engineer"
    return data["id"]


@pytest.mark.asyncio
async def test_list_jobs(client: AsyncClient, integration_id: str):
    await test_create_job(client, integration_id)
    resp = await client.get("/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["jobs"]) >= 1


@pytest.mark.asyncio
async def test_get_job(client: AsyncClient, integration_id: str):
    job_id = await test_create_job(client, integration_id)
    resp = await client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id


@pytest.mark.asyncio
async def test_job_not_found(client: AsyncClient):
    resp = await client.get("/jobs/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_queue_stats(client: AsyncClient):
    resp = await client.get("/jobs/stats/queue")
    assert resp.status_code == 200
    data = resp.json()
    assert "pending" in data
    assert "completed" in data
    assert "failed" in data
