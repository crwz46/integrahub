# IntegraHub — Enterprise API Integration Gateway

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-purple)](LICENSE)

**IntegraHub** is a production-ready API integration gateway built with FastAPI. It demonstrates enterprise integration patterns for connecting ATS, HRIS, and third-party APIs — exactly the kind of system used by integration engineers at companies like Integrity Indonesia.

## Features

### Core Capabilities

| Feature | Description |
|---------|-------------|
| **Multi-Provider Adapters** | Pluggable adapter pattern supporting Workday, Greenhouse, Lever, iCIMS |
| **Async Job Queue** | File-based priority queue with retries and status tracking |
| **Webhook Engine** | HMAC-SHA256 signing, exponential backoff retry, dead-letter queue |
| **OAuth2 Auth** | Client credentials flow + scoped API keys |
| **Developer Portal** | Built-in dashboard, API playground, live monitoring |
| **File Handling** | Upload/download with pre-signed URLs |

### Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Developer   │────▶│  IntegraHub  │────▶│  Workday API  │
│  Portal      │     │  Gateway     │     │  Greenhouse   │
│  (HTML/JS)   │     │  (FastAPI)   │     │  Lever        │
└─────────────┘     │              │     │  iCIMS        │
                    │  ┌────────┐  │     └──────────────┘
                    │  │ Queue  │  │
                    │  └────────┘  │     ┌──────────────┐
                    │  ┌────────┐  │────▶│  Webhooks     │
                    │  │Engine  │  │     │  (HMAC/Retry) │
                    │  └────────┘  │     └──────────────┘
                    └──────────────┘
```

## Quick Start

```bash
# Clone
git clone https://github.com/crwz46/integrahub.git
cd integrahub

# Install
pip install -r requirements.txt

# Run
uvicorn app.main:app --reload

# Open
open http://localhost:8000
```

Or with Docker:

```bash
docker compose up
```

## API Overview

### Authentication
```
POST /auth/token              # OAuth2 client credentials
POST /auth/api-keys           # Create API key
GET  /auth/api-keys           # List API keys
```

### Integrations
```
GET    /integrations            # List all integrations
POST   /integrations            # Create integration
GET    /integrations/{id}       # Get integration details
PUT    /integrations/{id}       # Update integration
DELETE /integrations/{id}       # Delete integration
GET    /integrations/{id}/test  # Test connection
```

### Jobs
```
POST  /jobs                # Submit job
GET   /jobs                # List jobs (?status=&page=&page_size=)
GET   /jobs/{id}           # Get job status
POST  /jobs/{id}/retry     # Retry failed job
GET   /jobs/stats/queue    # Queue stats
```

### Webhooks
```
POST  /webhooks/register          # Register webhook
GET   /webhooks/subscriptions     # List subscriptions
GET   /webhooks/deliveries        # Delivery logs
GET   /webhooks/dlq               # Dead-letter queue
POST  /webhooks/dlq/{id}/replay   # Replay failed delivery
```

### Reports
```
POST  /reports               # Generate integration report
GET   /reports               # List reports
GET   /reports/{id}          # Get report
```

## Full API Reference

Interactive docs at [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI) or [http://localhost:8000/redoc](http://localhost:8000/redoc) (ReDoc).

## Example Workflow

```python
# 1. Create a Workday integration
POST /integrations
{
  "name": "Production Workday",
  "provider": "workday",
  "api_base_url": "https://api.workday.com/v1"
}

# 2. Get client credentials from response
#    client_id: "ig_abc123..."
#    client_secret: "def456..."

# 3. Get access token
POST /auth/token
{
  "client_id": "ig_abc123...",
  "client_secret": "def456...",
  "grant_type": "client_credentials"
}
# → {"access_token": "eyJ...", "token_type": "Bearer", "expires_in": 3600}

# 4. Submit a job
POST /jobs
Authorization: Bearer eyJ...
{
  "integration_id": "int_abc...",
  "payload": {"title": "Senior Engineer", "location": "Jakarta"}
}

# 5. Check results
GET /jobs/job_abc...
```

## Project Structure

```
integrahub/
├── app/
│   ├── main.py              # FastAPI app + developer portal
│   ├── config.py            # Settings
│   ├── models.py            # Pydantic schemas
│   ├── api/
│   │   ├── integrations.py  # Integration CRUD
│   │   ├── jobs.py          # Job processing
│   │   ├── webhooks.py      # Webhook engine API
│   │   └── reports.py       # Analytics reports
│   ├── core/
│   │   ├── security.py      # OAuth2, JWT, HMAC, API keys
│   │   ├── queue.py         # Async job queue
│   │   └── webhook_engine.py# Webhook dispatch + retry + DLQ
│   └── adapters/
│       ├── base.py          # Abstract adapter interface
│       ├── workday.py       # Workday mock adapter
│       └── greenhouse.py    # Greenhouse mock adapter
├── tests/
│   ├── test_integrations.py
│   ├── test_jobs.py
│   ├── test_webhooks.py
│   └── test_auth.py
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Running Tests

```bash
pytest tests/ -v
```

## Skills Demonstrated

- REST API design (OpenAPI, versioning, error handling)
- OAuth2 client credentials flow + API key management
- Webhook engineering (HMAC signing, retry with backoff, DLQ)
- Pluggable adapter pattern (Strategy pattern)
- Async task queue with priority
- File handling with pre-signed URLs
- Developer portal with interactive playground
- Docker containerization
- Comprehensive test coverage

## License

MIT
