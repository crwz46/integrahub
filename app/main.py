import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
import jwt as pyjwt

from app.api import integrations, jobs, webhooks, reports
from app.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_api_key,
    generate_presigned_url,
    verify_client_credentials,
)
from app.models import (
    APIKey,
    APIKeyCreate,
    FileInfo,
    FileUploadResponse,
    HealthResponse,
    TokenRequest,
    TokenResponse,
)

api_keys_store: dict[str, dict] = {}
_integrations_path = Path(settings.data_path) / "integrations"
_files_path = Path(settings.data_path) / "uploads"
_files_path.mkdir(parents=True, exist_ok=True)

security = HTTPBearer(auto_error=False)

start_time = time.time()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window_seconds
        self.requests[client_ip] = [t for t in self.requests[client_ip] if t > window_start]

        if len(self.requests[client_ip]) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limit_exceeded", "message": f"Max {self.max_requests} requests per {self.window_seconds}s", "retry_after": self.window_seconds},
                headers={"Retry-After": str(self.window_seconds)},
            )

        self.requests[client_ip].append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(self.max_requests - len(self.requests[client_ip]))
        return response


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except HTTPException:
            raise
        except ValueError as e:
            return JSONResponse(status_code=422, content={"error": "validation_error", "message": str(e)})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "internal_error", "message": str(e) if settings.debug else "Internal server error"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    jobs.start_worker()
    yield
    jobs.stop_worker()
    await webhooks.engine.close()


app = FastAPI(
    title="IntegraHub",
    version=settings.app_version,
    description="Enterprise API Integration Gateway — Connect, Orchestrate, Monitor",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={"name": "IntegraHub Team", "url": "https://github.com/crwz46/integrahub"},
    license_info={"name": "MIT", "identifier": "MIT"},
)

app.add_middleware(RateLimitMiddleware, max_requests=200, window_seconds=60)
app.add_middleware(ErrorHandlerMiddleware)

app.include_router(integrations.router)
app.include_router(jobs.router)
app.include_router(webhooks.router)
app.include_router(reports.router)


async def get_current_client(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    if credentials is None:
        raise HTTPException(401, "Missing authentication")
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        for key_id, key_info in api_keys_store.items():
            if key_info.get("key") == token and key_info.get("active"):
                return {"client_id": key_id, "scopes": key_info.get("scopes", [])}
        raise HTTPException(401, "Invalid or expired token")
    return {"client_id": payload.get("sub"), "scopes": payload.get("scopes", [])}


# --- Auth Endpoints ---

@app.post("/auth/token", response_model=TokenResponse)
async def get_token(data: TokenRequest):
    for p in _integrations_path.glob("*.json"):
        import json
        with open(p) as f:
            integration = json.load(f)
        if integration["client_id"] == data.client_id:
            if verify_client_credentials(data.client_id, data.client_secret, integration["client_secret"]):
                token = create_access_token(data.client_id)
                return TokenResponse(access_token=token, expires_in=settings.jwt_expiry_minutes * 60)
    raise HTTPException(401, "Invalid client credentials")


@app.post("/auth/api-keys", response_model=APIKey, status_code=201)
async def create_api_key(data: APIKeyCreate):
    key_id = f"key_{uuid.uuid4().hex[:12]}"
    raw_key = generate_api_key()
    api_keys_store[key_id] = {
        "id": key_id,
        "name": data.name,
        "key": raw_key,
        "key_hash": hash_api_key(raw_key),
        "scopes": data.scopes,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return APIKey(
        id=key_id,
        name=data.name,
        key=raw_key,
        scopes=data.scopes,
        active=True,
        created_at=api_keys_store[key_id]["created_at"],
    )


@app.get("/auth/api-keys", response_model=list[APIKey])
async def list_api_keys():
    return [
        APIKey(
            id=info["id"],
            name=info["name"],
            key=info["key"][:12] + "..." if len(info["key"]) > 15 else info["key"],
            scopes=info["scopes"],
            active=info["active"],
            created_at=info["created_at"],
        )
        for info in api_keys_store.values()
    ]

# --- Files ---

@app.post("/files/upload", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = File(...)):
    file_id = f"file_{uuid.uuid4().hex[:12]}"
    content = await file.read()
    file_path = _files_path / f"{file_id}_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(content)
    presigned_url = generate_presigned_url(str(file_path))
    return FileUploadResponse(
        id=file_id,
        filename=file.filename or "unknown",
        size_bytes=len(content),
        content_type=file.content_type or "application/octet-stream",
        upload_url=f"/files/download/{file_id}?token={presigned_url}",
        expires_at=(datetime.now(timezone.utc)).isoformat(),
    )


@app.get("/files/{file_id}", response_model=FileInfo)
async def get_file_info(file_id: str):
    for p in _files_path.iterdir():
        if p.name.startswith(file_id):
            return FileInfo(
                id=file_id,
                filename=p.name[len(file_id) + 1:],
                size_bytes=p.stat().st_size,
                content_type="application/octet-stream",
                uploaded_at=datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
            )
    raise HTTPException(404, "File not found")


@app.get("/files/download/{file_id}")
async def download_file(file_id: str):
    for p in _files_path.iterdir():
        if p.name.startswith(file_id):
            return FileResponse(
                path=str(p),
                filename=p.name[len(file_id) + 1:],
                media_type="application/octet-stream",
            )
    raise HTTPException(404, "File not found")

# --- Health ---

@app.get("/health", response_model=HealthResponse)
async def health():
    uptime_seconds = int(time.time() - start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        uptime=f"{hours}h {minutes}m {seconds}s",
        integrations=len(list(_integrations_path.glob("*.json"))),
        jobs_processed=jobs.queue.stats().get("completed", 0),
        webhooks_delivered=len(webhooks.engine.get_deliveries()),
    )

# --- Developer Portal ---

DEV_PORTAL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IntegraHub — Developer Portal</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace; }
  .nav-link { @apply px-4 py-2 text-gray-400 hover:text-white transition-colors; }
  .nav-link.active { @apply text-cyan-400 border-b-2 border-cyan-400; }
  .stat-card { @apply bg-gray-800 rounded-xl p-6 border border-gray-700; }
  .code-block { @apply bg-gray-900 rounded-lg p-4 text-sm overflow-x-auto; }
  .endpoint { @apply flex items-center gap-3 p-3 bg-gray-800/50 rounded-lg border border-gray-700 hover:border-gray-500 transition-colors cursor-pointer; }
  .method { @apply px-2 py-1 text-xs font-bold rounded text-white; }
  .badge { @apply px-2 py-0.5 text-xs rounded-full; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  .fade-in { animation: fadeIn 0.3s ease-out; }
  .skeleton { @apply bg-gray-700 animate-pulse rounded; }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: #1a1a2e; }
  ::-webkit-scrollbar-thumb { background: #4a5568; border-radius: 3px; }
</style>
</head>
<body class="bg-gray-900 text-gray-100">
<nav class="border-b border-gray-800 bg-gray-900/95 backdrop-blur sticky top-0 z-50">
  <div class="max-w-7xl mx-auto px-4 flex items-center justify-between h-16">
    <div class="flex items-center gap-3">
      <div class="w-8 h-8 bg-gradient-to-br from-cyan-400 to-blue-600 rounded-lg flex items-center justify-center text-white font-bold text-sm">IH</div>
      <span class="text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">IntegraHub</span>
      <span class="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded-full">v1.0.0</span>
    </div>
    <div class="flex items-center gap-2">
      <a href="#" class="nav-link active" data-tab="overview">Overview</a>
      <a href="#" class="nav-link" data-tab="docs">API Docs</a>
      <a href="#" class="nav-link" data-tab="playground">Playground</a>
      <a href="#" class="nav-link" data-tab="monitor">Monitor</a>
    </div>
    <div>
      <span id="statusBadge" class="badge bg-green-900 text-green-300 border border-green-700">● All Systems</span>
    </div>
  </div>
</nav>

<main class="max-w-7xl mx-auto px-4 py-8">

<!-- OVERVIEW -->
<section id="tab-overview" class="tab-content">
  <div class="mb-8">
    <h1 class="text-3xl font-bold mb-2">Enterprise API Integration Gateway</h1>
    <p class="text-gray-400 max-w-3xl">Connect any ATS, HRIS, or third-party API with enterprise-grade reliability. OAuth2, webhooks with HMAC signing, async job processing, and dead-letter queues built in.</p>
  </div>

  <div class="grid grid-cols-4 gap-4 mb-8" id="statsGrid">
    <div class="stat-card"><div class="text-gray-400 text-sm">Integrations</div><div class="text-3xl font-bold text-cyan-400" id="statIntegrations">—</div></div>
    <div class="stat-card"><div class="text-gray-400 text-sm">Jobs Processed</div><div class="text-3xl font-bold text-green-400" id="statJobs">—</div></div>
    <div class="stat-card"><div class="text-gray-400 text-sm">Webhooks Sent</div><div class="text-3xl font-bold text-blue-400" id="statWebhooks">—</div></div>
    <div class="stat-card"><div class="text-gray-400 text-sm">Uptime</div><div class="text-3xl font-bold text-purple-400" id="statUptime">—</div></div>
  </div>

  <div class="grid grid-cols-2 gap-6">
    <div class="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <h2 class="text-lg font-semibold mb-4">Quick Start</h2>
      <pre class="code-block"><code class="language-bash"># Get access token
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"YOUR_CLIENT_ID","client_secret":"YOUR_SECRET","grant_type":"client_credentials"}'

# Create an integration
curl -X POST http://localhost:8000/integrations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"My Workday","provider":"workday","api_base_url":"https://api.workday.com/v1"}'

# Submit a job
curl -X POST http://localhost:8000/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"integration_id":"int_...","payload":{"title":"Senior Engineer","location":"Remote"}}'

# Check delivery logs
curl http://localhost:8000/webhooks/deliveries \
  -H "Authorization: Bearer $TOKEN"</code></pre>
    </div>
    <div class="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <h2 class="text-lg font-semibold mb-4">Key Capabilities</h2>
      <div class="space-y-4">
        <div class="flex gap-3"><div class="w-6 h-6 bg-cyan-900/50 text-cyan-400 rounded flex items-center justify-center text-sm shrink-0">1</div><div><strong class="text-white">Multi-Provider Adapters</strong><p class="text-gray-400 text-sm">Workday, Greenhouse, Lever, iCIMS — pluggable adapter pattern with health checks.</p></div></div>
        <div class="flex gap-3"><div class="w-6 h-6 bg-green-900/50 text-green-400 rounded flex items-center justify-center text-sm shrink-0">2</div><div><strong class="text-white">Async Job Queue</strong><p class="text-gray-400 text-sm">File-based priority queue with retries, dead-letter handling, and status tracking.</p></div></div>
        <div class="flex gap-3"><div class="w-6 h-6 bg-blue-900/50 text-blue-400 rounded flex items-center justify-center text-sm shrink-0">3</div><div><strong class="text-white">Secure Webhooks</strong><p class="text-gray-400 text-sm">HMAC-SHA256 signed payloads, automatic retry with exponential backoff, delivery logs.</p></div></div>
        <div class="flex gap-3"><div class="w-6 h-6 bg-purple-900/50 text-purple-400 rounded flex items-center justify-center text-sm shrink-0">4</div><div><strong class="text-white">OAuth2 + API Keys</strong><p class="text-gray-400 text-sm">Client credentials flow, bearer token auth, scoped API keys with audit logging.</p></div></div>
      </div>
    </div>
  </div>
</section>

<!-- API DOCS -->
<section id="tab-docs" class="tab-content hidden">
  <div class="mb-6">
    <h1 class="text-2xl font-bold mb-2">API Reference</h1>
    <p class="text-gray-400">All endpoints require <code class="bg-gray-800 px-2 py-0.5 rounded text-cyan-400">Authorization: Bearer &lt;token&gt;</code> unless noted.</p>
  </div>
  <div class="space-y-6" id="apiEndpoints">
    <div>
      <h2 class="text-lg font-semibold mb-3 text-cyan-400">Authentication</h2>
      <div class="endpoint" data-path="/auth/token" data-method="POST"><span class="method bg-green-600">POST</span><code class="text-sm">/auth/token</code><span class="text-gray-500 text-sm ml-auto">Get OAuth2 access token</span></div>
    </div>
    <div>
      <h2 class="text-lg font-semibold mb-3 text-cyan-400">Integrations</h2>
      <div class="endpoint" data-path="/integrations" data-method="GET"><span class="method bg-blue-600">GET</span><code class="text-sm">/integrations</code><span class="text-gray-500 text-sm ml-auto">List all integrations</span></div>
      <div class="endpoint" data-path="/integrations" data-method="POST"><span class="method bg-green-600">POST</span><code class="text-sm">/integrations</code><span class="text-gray-500 text-sm ml-auto">Create a new integration</span></div>
      <div class="endpoint" data-path="/integrations/{id}" data-method="GET"><span class="method bg-blue-600">GET</span><code class="text-sm">/integrations/{id}</code><span class="text-gray-500 text-sm ml-auto">Get integration details</span></div>
      <div class="endpoint" data-path="/integrations/{id}" data-method="DELETE"><span class="method bg-red-600">DELETE</span><code class="text-sm">/integrations/{id}</code><span class="text-gray-500 text-sm ml-auto">Delete an integration</span></div>
      <div class="endpoint" data-path="/integrations/{id}/test" data-method="GET"><span class="method bg-yellow-600">GET</span><code class="text-sm">/integrations/{id}/test</code><span class="text-gray-500 text-sm ml-auto">Test connection to provider</span></div>
    </div>
    <div>
      <h2 class="text-lg font-semibold mb-3 text-cyan-400">Jobs</h2>
      <div class="endpoint" data-path="/jobs" data-method="POST"><span class="method bg-green-600">POST</span><code class="text-sm">/jobs</code><span class="text-gray-500 text-sm ml-auto">Submit a job for processing</span></div>
      <div class="endpoint" data-path="/jobs" data-method="GET"><span class="method bg-blue-600">GET</span><code class="text-sm">/jobs</code><span class="text-gray-500 text-sm ml-auto">List jobs (filter by status)</span></div>
      <div class="endpoint" data-path="/jobs/{id}" data-method="GET"><span class="method bg-blue-600">GET</span><code class="text-sm">/jobs/{id}</code><span class="text-gray-500 text-sm ml-auto">Get job status & result</span></div>
      <div class="endpoint" data-path="/jobs/{id}/retry" data-method="POST"><span class="method bg-yellow-600">POST</span><code class="text-sm">/jobs/{id}/retry</code><span class="text-gray-500 text-sm ml-auto">Retry failed job</span></div>
    </div>
    <div>
      <h2 class="text-lg font-semibold mb-3 text-cyan-400">Webhooks</h2>
      <div class="endpoint" data-path="/webhooks/register" data-method="POST"><span class="method bg-green-600">POST</span><code class="text-sm">/webhooks/register</code><span class="text-gray-500 text-sm ml-auto">Register webhook subscription</span></div>
      <div class="endpoint" data-path="/webhooks/subscriptions" data-method="GET"><span class="method bg-blue-600">GET</span><code class="text-sm">/webhooks/subscriptions</code><span class="text-gray-500 text-sm ml-auto">List subscriptions</span></div>
      <div class="endpoint" data-path="/webhooks/deliveries" data-method="GET"><span class="method bg-blue-600">GET</span><code class="text-sm">/webhooks/deliveries</code><span class="text-gray-500 text-sm ml-auto">Webhook delivery logs</span></div>
      <div class="endpoint" data-path="/webhooks/dlq/replay" data-method="POST"><span class="method bg-orange-600">POST</span><code class="text-sm">/webhooks/dlq/{id}/replay</code><span class="text-gray-500 text-sm ml-auto">Replay from dead-letter queue</span></div>
    </div>
    <div>
      <h2 class="text-lg font-semibold mb-3 text-cyan-400">Reports & Analytics</h2>
      <div class="endpoint" data-path="/reports" data-method="POST"><span class="method bg-green-600">POST</span><code class="text-sm">/reports</code><span class="text-gray-500 text-sm ml-auto">Generate integration report</span></div>
      <div class="endpoint" data-path="/reports" data-method="GET"><span class="method bg-blue-600">GET</span><code class="text-sm">/reports</code><span class="text-gray-500 text-sm ml-auto">List all reports</span></div>
    </div>
  </div>
</section>

<!-- PLAYGROUND -->
<section id="tab-playground" class="tab-content hidden">
  <div class="mb-6">
    <h1 class="text-2xl font-bold mb-2">API Playground</h1>
    <p class="text-gray-400">Test endpoints directly from your browser.</p>
  </div>
  <div class="grid grid-cols-3 gap-6">
    <div class="col-span-1 bg-gray-800 rounded-xl p-4 border border-gray-700">
      <h3 class="font-semibold mb-3">Endpoint</h3>
      <select id="playMethod" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm mb-2">
        <option value="GET">GET</option>
        <option value="POST">POST</option>
        <option value="PUT">PUT</option>
        <option value="DELETE">DELETE</option>
      </select>
      <input id="playPath" type="text" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm mb-3 font-mono" placeholder="/integrations" value="/health">
      <h3 class="font-semibold mb-2 text-sm">Body (JSON)</h3>
      <textarea id="playBody" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono h-32" placeholder='{"key": "value"}'></textarea>
      <button onclick="sendRequest()" class="mt-3 w-full bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg px-4 py-2 text-sm font-semibold transition-colors">Send Request</button>
    </div>
    <div class="col-span-2 bg-gray-800 rounded-xl p-4 border border-gray-700">
      <h3 class="font-semibold mb-3">Response</h3>
      <pre id="playResponse" class="code-block min-h-[300px]"><code class="language-json">// Response will appear here...</code></pre>
      <div class="flex gap-2 mt-2 text-sm text-gray-500">
        <span>Status: <span id="playStatus" class="text-white">—</span></span>
        <span>Time: <span id="playTime" class="text-white">—</span></span>
      </div>
    </div>
  </div>
</section>

<!-- MONITOR -->
<section id="tab-monitor" class="tab-content hidden">
  <div class="mb-6">
    <h1 class="text-2xl font-bold mb-2">System Monitor</h1>
    <p class="text-gray-400">Real-time metrics and dead-letter queue management.</p>
  </div>
  <div class="grid grid-cols-2 gap-6">
    <div class="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <h2 class="text-lg font-semibold mb-4">Queue Status</h2>
      <div id="queueStats" class="space-y-3">
        <div class="flex justify-between"><span class="text-gray-400">Pending</span><span class="text-yellow-400 font-mono" id="qPending">0</span></div>
        <div class="flex justify-between"><span class="text-gray-400">Processing</span><span class="text-blue-400 font-mono" id="qProcessing">0</span></div>
        <div class="flex justify-between"><span class="text-gray-400">Completed</span><span class="text-green-400 font-mono" id="qCompleted">0</span></div>
        <div class="flex justify-between"><span class="text-gray-400">Failed</span><span class="text-red-400 font-mono" id="qFailed">0</span></div>
      </div>
    </div>
    <div class="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <h2 class="text-lg font-semibold mb-4">Dead-Letter Queue</h2>
      <div id="dlqContent" class="text-gray-400 text-sm">No failed deliveries</div>
    </div>
  </div>
</section>
</main>

<script>
const BASE = 'http://localhost:8000';
let token = null;

// Tab switching
document.querySelectorAll('[data-tab]').forEach(el => {
  el.addEventListener('click', e => {
    e.preventDefault();
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    el.classList.add('active');
    document.querySelectorAll('.tab-content').forEach(t => t.classList.add('hidden'));
    document.getElementById('tab-' + el.dataset.tab).classList.remove('hidden');
  });
});

// Fetch stats
async function loadStats() {
  try {
    const r = await fetch(BASE + '/health');
    const d = await r.json();
    document.getElementById('statIntegrations').textContent = d.integrations;
    document.getElementById('statJobs').textContent = d.jobs_processed;
    document.getElementById('statWebhooks').textContent = d.webhooks_delivered;
    document.getElementById('statUptime').textContent = d.uptime;
  } catch(e) {
    document.getElementById('statusBadge').className = 'badge bg-red-900 text-red-300 border border-red-700';
    document.getElementById('statusBadge').textContent = '● Disconnected';
  }
}
loadStats();
setInterval(loadStats, 5000);

// Queue stats
async function loadQueueStats() {
  try {
    const r = await fetch(BASE + '/jobs/stats/queue');
    const d = await r.json();
    document.getElementById('qPending').textContent = d.pending;
    document.getElementById('qProcessing').textContent = d.processing;
    document.getElementById('qCompleted').textContent = d.completed;
    document.getElementById('qFailed').textContent = d.failed;
  } catch(e) {}
}
loadQueueStats();
setInterval(loadQueueStats, 3000);

// Playground
async function sendRequest() {
  const method = document.getElementById('playMethod').value;
  const path = document.getElementById('playPath').value;
  const body = document.getElementById('playBody').value;
  const start = performance.now();

  const el = document.getElementById('playResponse');
  el.innerHTML = '<code class="text-gray-500">Loading...</code>';

  try {
    const opts = { method, headers: {'Content-Type': 'application/json'} };
    if (token) opts.headers['Authorization'] = 'Bearer ' + token;
    if (body.trim()) opts.body = body;

    const r = await fetch(BASE + path, opts);
    const time = Math.round(performance.now() - start);
    document.getElementById('playStatus').textContent = r.status + ' ' + r.statusText;
    document.getElementById('playTime').textContent = time + 'ms';

    const text = await r.text();
    try {
      const json = JSON.stringify(JSON.parse(text), null, 2);
      el.innerHTML = '<code class="language-json">' + escapeHtml(json) + '</code>';
    } catch(e) {
      el.innerHTML = '<code>' + escapeHtml(text) + '</code>';
    }
    hljs.highlightElement(el.querySelector('code'));
  } catch(e) {
    document.getElementById('playStatus').textContent = 'ERROR';
    el.innerHTML = '<code class="language-json text-red-400">' + escapeHtml(e.message) + '</code>';
  }
}

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Quick auto-auth: try to get a token via demo endpoint hint
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def developer_portal():
    return DEV_PORTAL_HTML

@app.get("/playground", include_in_schema=False)
async def playground_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/")
