import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.adapters import AdapterRegistry
from app.config import settings
from app.core.security import generate_client_credentials
from app.models import Integration, IntegrationCreate, IntegrationUpdate

router = APIRouter(prefix="/integrations", tags=["Integrations"])
_storage = Path(settings.data_path) / "integrations"
_storage.mkdir(parents=True, exist_ok=True)


def _save(integration: dict):
    with open(_storage / f"{integration['id']}.json", "w") as f:
        json.dump(integration, f)


def _load(integration_id: str) -> dict | None:
    path = _storage / f"{integration_id}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def _load_all() -> list[dict]:
    integrations = []
    for p in _storage.glob("*.json"):
        with open(p) as f:
            integrations.append(json.load(f))
    return sorted(integrations, key=lambda x: x["created_at"], reverse=True)


@router.get("", response_model=list[Integration])
async def list_integrations():
    return _load_all()


@router.post("", response_model=Integration, status_code=201)
async def create_integration(data: IntegrationCreate):
    integration_id = f"int_{uuid.uuid4().hex[:12]}"
    client_id, client_secret = generate_client_credentials()
    now = datetime.now(timezone.utc).isoformat()
    integration = {
        "id": integration_id,
        "name": data.name,
        "provider": data.provider.value,
        "api_base_url": data.api_base_url,
        "api_version": data.api_version,
        "config": data.config,
        "status": "active",
        "client_id": client_id,
        "client_secret": client_secret,
        "created_at": now,
        "updated_at": now,
    }
    _save(integration)
    return integration


@router.get("/{integration_id}", response_model=Integration)
async def get_integration(integration_id: str):
    integration = _load(integration_id)
    if not integration:
        raise HTTPException(404, "Integration not found")
    return integration


@router.put("/{integration_id}", response_model=Integration)
async def update_integration(integration_id: str, data: IntegrationUpdate):
    integration = _load(integration_id)
    if not integration:
        raise HTTPException(404, "Integration not found")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None and key in ("name", "api_base_url", "api_version", "config", "status"):
            if key == "status":
                integration[key] = value.value if hasattr(value, "value") else value
            else:
                integration[key] = value
    integration["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(integration)
    return integration


@router.delete("/{integration_id}", status_code=204)
async def delete_integration(integration_id: str):
    integration = _load(integration_id)
    if not integration:
        raise HTTPException(404, "Integration not found")
    path = _storage / f"{integration_id}.json"
    path.unlink()


@router.get("/{integration_id}/test")
async def test_connection(integration_id: str):
    integration = _load(integration_id)
    if not integration:
        raise HTTPException(404, "Integration not found")
    try:
        adapter = AdapterRegistry.get(integration["provider"], integration["config"])
        result = await adapter.health_check()
        return {"status": "success", "detail": result}
    except Exception as e:
        raise HTTPException(502, f"Connection failed: {e}")


@router.get("/providers/list")
async def list_providers():
    return {"providers": AdapterRegistry.list_providers()}
