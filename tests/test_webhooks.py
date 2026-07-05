import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_register_webhook(client: AsyncClient):
    resp = await client.post(
        "/webhooks/register",
        json={
            "url": "https://hooks.example.com/integrahub",
            "events": ["job.submitted", "job.completed"],
            "description": "Test webhook",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["url"] == "https://hooks.example.com/integrahub"
    assert len(data["events"]) == 2
    assert "secret" in data
    assert data["active"] is True
    return data


@pytest.mark.asyncio
async def test_list_subscriptions(client: AsyncClient):
    await test_register_webhook(client)
    resp = await client.get("/webhooks/subscriptions")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_list_deliveries(client: AsyncClient):
    resp = await client.get("/webhooks/deliveries")
    assert resp.status_code == 200
    data = resp.json()
    assert "deliveries" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_delete_subscription(client: AsyncClient):
    sub = await test_register_webhook(client)
    resp = await client.delete(f"/webhooks/subscriptions/{sub['id']}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_dlq_empty(client: AsyncClient):
    resp = await client.get("/webhooks/dlq")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
