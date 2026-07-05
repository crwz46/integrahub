from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProviderType(str, Enum):
    workday = "workday"
    greenhouse = "greenhouse"
    lever = "lever"
    icims = "icims"
    custom = "custom"


class IntegrationStatus(str, Enum):
    active = "active"
    paused = "paused"
    error = "error"
    disconnected = "disconnected"


class JobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    retrying = "retrying"


class WebhookEvent(str, Enum):
    job_submitted = "job.submitted"
    job_completed = "job.completed"
    job_failed = "job.failed"
    status_changed = "status.changed"
    adverse_action = "adverse.action"
    document_received = "document.received"


# --- Integration Models ---

class IntegrationBase(BaseModel):
    name: str
    provider: ProviderType
    api_base_url: str
    api_version: str = "v1"
    config: dict = {}


class IntegrationCreate(IntegrationBase):
    pass


class IntegrationUpdate(BaseModel):
    name: Optional[str] = None
    api_base_url: Optional[str] = None
    api_version: Optional[str] = None
    config: Optional[dict] = None
    status: Optional[IntegrationStatus] = None


class Integration(IntegrationBase):
    id: str
    status: IntegrationStatus = IntegrationStatus.active
    client_id: str
    client_secret: str
    created_at: str
    updated_at: str


# --- Job Models ---

class JobCreate(BaseModel):
    integration_id: str
    payload: dict
    priority: int = Field(default=0, ge=0, le=100)
    webhook_url: Optional[str] = None


class Job(BaseModel):
    id: str
    integration_id: str
    status: JobStatus
    payload: dict
    result: Optional[dict] = None
    error: Optional[str] = None
    attempts: int = 0
    priority: int = 0
    webhook_url: Optional[str] = None
    created_at: str
    updated_at: str


class JobListResponse(BaseModel):
    jobs: list[Job]
    total: int
    page: int
    page_size: int


# --- Webhook Models ---

class WebhookDelivery(BaseModel):
    id: str
    event: WebhookEvent
    url: str
    payload: dict
    signature: str
    status: str
    attempts: int
    last_attempt: Optional[str] = None
    next_retry: Optional[str] = None
    response_status: Optional[int] = None
    error: Optional[str] = None


class WebhookRegister(BaseModel):
    url: str
    events: list[WebhookEvent]
    secret: Optional[str] = None
    description: Optional[str] = None


class WebhookSubscription(BaseModel):
    id: str
    url: str
    events: list[WebhookEvent]
    secret: str
    description: Optional[str] = None
    active: bool = True
    created_at: str


class WebhookLogResponse(BaseModel):
    deliveries: list[WebhookDelivery]
    total: int


# --- Report Models ---

class ReportRequest(BaseModel):
    integration_id: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    format: str = "json"


class Report(BaseModel):
    id: str
    integration_id: str
    status: JobStatus
    total_jobs: int
    success_rate: float
    avg_processing_time_ms: float
    generated_at: str
    data: Optional[dict] = None


# --- Auth Models ---

class TokenRequest(BaseModel):
    client_id: str
    client_secret: str
    grant_type: str = "client_credentials"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class APIKeyCreate(BaseModel):
    name: str
    scopes: list[str] = ["integrations:read", "jobs:write"]


class APIKey(BaseModel):
    id: str
    name: str
    key: str
    scopes: list[str]
    active: bool = True
    created_at: str


# --- File Models ---

class FileUploadResponse(BaseModel):
    id: str
    filename: str
    size_bytes: int
    content_type: str
    upload_url: str
    expires_at: str


class FileInfo(BaseModel):
    id: str
    filename: str
    size_bytes: int
    content_type: str
    uploaded_at: str


# --- Generic ---

class HealthResponse(BaseModel):
    status: str
    version: str
    uptime: str
    integrations: int
    jobs_processed: int
    webhooks_delivered: int
