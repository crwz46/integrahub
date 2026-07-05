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
async def test_create_api_key(client: AsyncClient):
    resp = await client.post(
        "/auth/api-keys",
        json={"name": "Test Key", "scopes": ["integrations:read", "jobs:write"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Key"
    assert data["key"].startswith("ihk_")
    assert data["active"] is True
    return data["id"]


@pytest.mark.asyncio
async def test_list_api_keys(client: AsyncClient):
    await test_create_api_key(client)
    resp = await client.get("/auth/api-keys")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_token_endpoint_requires_valid_credentials(client: AsyncClient):
    resp = await client.post(
        "/auth/token",
        json={
            "client_id": "nonexistent",
            "client_secret": "bad-secret",
            "grant_type": "client_credentials",
        },
    )
    assert resp.status_code == 401
