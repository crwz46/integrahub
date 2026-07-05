import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from app.config import settings
from app.core.security import sign_webhook_payload


class WebhookEngine:
    def __init__(self, data_path: Optional[str] = None):
        self.base_path = Path(data_path or settings.data_path) / "webhooks"
        self._deliveries_path = self.base_path / "deliveries"
        self._dlq_path = self.base_path / "dlq"
        self._subscriptions_path = self.base_path / "subscriptions"
        for p in [self._deliveries_path, self._dlq_path, self._subscriptions_path]:
            p.mkdir(parents=True, exist_ok=True)
        self._client = httpx.AsyncClient(timeout=10)

    def register_subscription(self, url: str, events: list[str], secret: str, description: Optional[str] = None) -> dict:
        sub_id = f"whsub_{uuid.uuid4().hex[:12]}"
        sub = {
            "id": sub_id,
            "url": url,
            "events": events,
            "secret": secret,
            "description": description,
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self._subscriptions_path / f"{sub_id}.json", "w") as f:
            json.dump(sub, f)
        return sub

    def list_subscriptions(self) -> list[dict]:
        subs = []
        for p in self._subscriptions_path.glob("*.json"):
            with open(p) as f:
                subs.append(json.load(f))
        return subs

    def get_subscription(self, sub_id: str) -> Optional[dict]:
        path = self._subscriptions_path / f"{sub_id}.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    def delete_subscription(self, sub_id: str):
        path = self._subscriptions_path / f"{sub_id}.json"
        path.unlink(missing_ok=True)

    def _save_delivery(self, delivery: dict):
        with open(self._deliveries_path / f"{delivery['id']}.json", "w") as f:
            json.dump(delivery, f)

    async def dispatch(self, event: str, payload: dict):
        subs = self.list_subscriptions()
        tasks = []
        for sub in subs:
            if sub["active"] and event in sub["events"]:
                tasks.append(self._deliver(sub, event, payload))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _deliver(self, subscription: dict, event: str, payload: dict):
        delivery_id = f"whd_{uuid.uuid4().hex[:12]}"
        body = {"event": event, "payload": payload, "delivery_id": delivery_id, "timestamp": datetime.now(timezone.utc).isoformat()}
        signature = sign_webhook_payload(body, subscription["secret"])

        delivery: dict = {
            "id": delivery_id,
            "event": event,
            "url": subscription["url"],
            "payload": body,
            "signature": signature,
            "status": "pending",
            "attempts": 0,
            "max_attempts": settings.webhook_retry_max_attempts,
            "last_attempt": None,
            "next_retry": None,
            "response_status": None,
            "error": None,
            "subscription_id": subscription["id"],
        }

        for attempt in range(1, settings.webhook_retry_max_attempts + 1):
            delivery["attempts"] = attempt
            delivery["last_attempt"] = datetime.now(timezone.utc).isoformat()
            try:
                resp = await self._client.post(
                    subscription["url"],
                    json=body,
                    headers={
                        settings.webhook_signature_header: signature,
                        "Content-Type": "application/json",
                        "User-Agent": "IntegraHub-Webhook/1.0",
                        "X-Delivery-Id": delivery_id,
                    },
                )
                delivery["response_status"] = resp.status_code
                if 200 <= resp.status_code < 300:
                    delivery["status"] = "delivered"
                    self._save_delivery(delivery)
                    return
                delivery["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as e:
                delivery["error"] = str(e)

            if attempt < settings.webhook_retry_max_attempts:
                delay = settings.webhook_retry_base_delay_seconds * (2 ** (attempt - 1))
                delivery["next_retry"] = datetime.now(timezone.utc).timestamp() + delay
                self._save_delivery(delivery)
                await asyncio.sleep(delay)
            else:
                delivery["status"] = "failed"
                self._save_delivery(delivery)
                self._send_to_dlq(delivery)

    def _send_to_dlq(self, delivery: dict):
        with open(self._dlq_path / f"{delivery['id']}.json", "w") as f:
            json.dump(delivery, f)

    def get_deliveries(self, limit: int = 50) -> list[dict]:
        paths = sorted(
            self._deliveries_path.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]
        result = []
        for p in paths:
            with open(p) as f:
                result.append(json.load(f))
        return result

    def get_dlq(self) -> list[dict]:
        result = []
        for p in self._dlq_path.glob("*.json"):
            with open(p) as f:
                result.append(json.load(f))
        return result

    def replay_dlq(self, delivery_id: str):
        path = self._dlq_path / f"{delivery_id}.json"
        if path.exists():
            with open(path) as f:
                delivery = json.load(f)
            path.unlink()
            delivery["attempts"] = 0
            delivery["status"] = "pending"
            self._save_delivery(delivery)

    async def close(self):
        await self._client.aclose()
