"""
Seed IntegraHub with demo data -- integrations, jobs, webhooks, reports.

Run: python scripts/seed_demo.py
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.integrations import _save
from app.api.jobs import _save_job, queue
from app.core.security import generate_client_credentials
from app.core.webhook_engine import WebhookEngine
from app.models import IntegrationStatus

DEMO_INTEGRATIONS = [
    {
        "name": "Production Workday",
        "provider": "workday",
        "api_base_url": "https://api.workday.com/v1",
        "config": {"tenant": "acme_corp", "rate_limit": 100},
    },
    {
        "name": "Staging Greenhouse",
        "provider": "greenhouse",
        "api_base_url": "https://api.greenhouse.io/v1",
        "config": {"board_token": "acme-staging"},
    },
    {
        "name": "Lever Sandbox",
        "provider": "lever",
        "api_base_url": "https://api.lever.co/v1",
        "config": {"sandbox": True},
    },
    {
        "name": "iCIMS Production",
        "provider": "icims",
        "api_base_url": "https://api.icims.com/v1",
        "config": {"customer_id": "acme_123"},
    },
    {
        "name": "Custom HRIS Bridge",
        "provider": "custom",
        "api_base_url": "https://hris.acme.internal/api/v2",
        "config": {"webhook_secret": "whsec_demo123"},
    },
]

DEMO_JOBS = [
    {
        "title": "Senior Backend Engineer",
        "location": "Jakarta",
        "department": "Engineering",
        "employment_type": "full-time",
    },
    {
        "title": "API Integration Engineer",
        "location": "Remote",
        "department": "Integration",
        "employment_type": "full-time",
    },
    {
        "title": "DevOps Lead",
        "location": "Singapore",
        "department": "Infrastructure",
        "employment_type": "full-time",
    },
    {
        "title": "Product Designer",
        "location": "Jakarta",
        "department": "Design",
        "employment_type": "contract",
    },
    {
        "title": "Data Analyst",
        "location": "Surabaya",
        "department": "Data",
        "employment_type": "full-time",
    },
]


def seed():
    now = datetime.now(timezone.utc).isoformat()
    integration_ids = []

    print("[Seed] Seeding IntegraHub demo data...\n")

    for idx, int_data in enumerate(DEMO_INTEGRATIONS):
        int_id = f"int_demo_{uuid.uuid4().hex[:12]}"
        client_id, client_secret = generate_client_credentials()
        integration = {
            "id": int_id,
            "name": int_data["name"],
            "provider": int_data["provider"],
            "api_base_url": int_data["api_base_url"],
            "api_version": "v1",
            "config": int_data["config"],
            "status": IntegrationStatus.active.value,
            "client_id": client_id,
            "client_secret": client_secret,
            "created_at": now,
            "updated_at": now,
        }
        _save(integration)
        integration_ids.append(int_id)
        print(f"  [+] Integration: {int_data['name']} ({int_data['provider']})")

    statuses = ["completed", "completed", "completed", "completed", "failed"]
    for idx, job_data in enumerate(DEMO_JOBS):
        int_id = integration_ids[idx % len(integration_ids)]
        job_id = f"job_demo_{uuid.uuid4().hex[:12]}"
        job = {
            "id": job_id,
            "integration_id": int_id,
            "status": statuses[idx] if idx < len(statuses) else "completed",
            "payload": job_data,
            "result": {
                "provider_job_id": f"ext-{uuid.uuid4().hex[:8]}",
                "status": "published",
                "requisition_id": f"REQ-{uuid.uuid4().hex[:6].upper()}",
                "timestamp": now,
            } if idx != 4 else None,
            "error": "Rate limit exceeded. Retry in 60s." if idx == 4 else None,
            "attempts": 3 if idx == 4 else 1,
            "priority": 0,
            "webhook_url": None,
            "created_at": now,
            "updated_at": now,
        }
        _save_job(job)
        queue.enqueue("ats_job", {"job_id": job_id, "integration_id": int_id})
        print(f"  [+] Job: {job_data['title']} -- {job['status']}")

    webhook_data = [
        {
            "url": "https://hooks.acme.com/integrahub/jobs",
            "events": ["job.submitted", "job.completed", "job.failed"],
            "description": "Main job events webhook",
        },
        {
            "url": "https://hooks.acme.com/integrahub/status",
            "events": ["status.changed"],
            "description": "Status change notifications",
        },
    ]
    engine = WebhookEngine()
    for wh in webhook_data:
        engine.register_subscription(
            url=wh["url"],
            events=wh["events"],
            secret="whsec_demo_secret_123",
            description=wh["description"],
        )
        print(f"  [+] Webhook: {wh['description']} -> {wh['url']}")

    print("\n[OK] Demo data seeded!")
    print(f"     - {len(DEMO_INTEGRATIONS)} integrations")
    print(f"     - {len(DEMO_JOBS)} jobs")
    print(f"     - {len(webhook_data)} webhook subscriptions")
    print("\n     Open http://localhost:8000 to see the results!")
    print("     API docs at http://localhost:8000/docs")


if __name__ == "__main__":
    seed()
