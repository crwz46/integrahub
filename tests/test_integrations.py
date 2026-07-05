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
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_list_providers(client: AsyncClient):
    resp = await client.get("/integrations/providers/list")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert len(data["providers"]) >= 2


@pytest.mark.asyncio
async def test_create_integration(client: AsyncClient):
    resp = await client.post(
        "/integrations",
        json={
            "name": "Test Workday",
            "provider": "workday",
            "api_base_url": "https://api.workday.com/v1",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Workday"
    assert data["provider"] == "workday"
    assert "client_id" in data
    assert "client_secret" in data
    assert data["status"] == "active"
    return data["id"]


@pytest.mark.asyncio
async def test_get_integration(client: AsyncClient):
    created = await test_create_integration(client)
    resp = await client.get(f"/integrations/{created}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created


@pytest.mark.asyncio
async def test_list_integrations(client: AsyncClient):
    await test_create_integration(client)
    resp = await client.get("/integrations")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_delete_integration(client: AsyncClient):
    created = await test_create_integration(client)
    resp = await client.delete(f"/integrations/{created}")
    assert resp.status_code == 204
    resp = await client.get(f"/integrations/{created}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_test_connection(client: AsyncClient):
    created = await test_create_integration(client)
    resp = await client.get(f"/integrations/{created}/test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"


@pytest.mark.asyncio
async def test_create_integration_invalid_provider(client: AsyncClient):
    resp = await client.post(
        "/integrations",
        json={
            "name": "Bad Provider",
            "provider": "nonexistent",
            "api_base_url": "https://example.com",
        },
    )
    # Should fail validation
    assert resp.status_code == 422
