import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.core.webhook_engine import WebhookEngine
from app.models import WebhookDelivery, WebhookLogResponse, WebhookRegister, WebhookSubscription

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

engine = WebhookEngine()


@router.post("/register", response_model=WebhookSubscription, status_code=201)
async def register_webhook(data: WebhookRegister):
    secret = data.secret or uuid.uuid4().hex
    sub = engine.register_subscription(
        url=data.url,
        events=[e.value for e in data.events],
        secret=secret,
        description=data.description,
    )
    return sub


@router.get("/subscriptions", response_model=list[WebhookSubscription])
async def list_subscriptions():
    return engine.list_subscriptions()


@router.delete("/subscriptions/{sub_id}", status_code=204)
async def delete_subscription(sub_id: str):
    sub = engine.get_subscription(sub_id)
    if not sub:
        raise HTTPException(404, "Subscription not found")
    engine.delete_subscription(sub_id)


@router.get("/deliveries", response_model=WebhookLogResponse)
async def list_deliveries():
    deliveries = engine.get_deliveries()
    return {"deliveries": deliveries, "total": len(deliveries)}


@router.post("/{sub_id}/test", status_code=200)
async def test_webhook(sub_id: str):
    sub = engine.get_subscription(sub_id)
    if not sub:
        raise HTTPException(404, "Subscription not found")
    test_payload = {
        "test": True,
        "message": "This is a test webhook from IntegraHub",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await engine.dispatch("webhook.test", test_payload)
    return {"status": "dispatched", "url": sub["url"]}


@router.get("/dlq", response_model=list[WebhookDelivery])
async def list_dlq():
    return engine.get_dlq()


@router.post("/dlq/{delivery_id}/replay", status_code=200)
async def replay_dlq(delivery_id: str):
    engine.replay_dlq(delivery_id)
    return {"status": "replayed", "delivery_id": delivery_id}
