import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from app.config import settings


def generate_client_credentials() -> tuple[str, str]:
    client_id = f"ig_{uuid.uuid4().hex[:16]}"
    client_secret = uuid.uuid4().hex + uuid.uuid4().hex
    return client_id, client_secret


def create_access_token(client_id: str, scopes: list[str] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": client_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
        "scopes": scopes or ["integrations:read", "jobs:write"],
        "token_type": "access",
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        return pyjwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except pyjwt.PyJWTError:
        return None


def verify_client_credentials(client_id: str, client_secret: str, stored_secret: str) -> bool:
    return hmac.compare_digest(client_secret, stored_secret)


def sign_webhook_payload(payload: dict, secret: str) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    signature = hmac.new(
        secret.encode(),
        body.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={signature}"


def verify_webhook_signature(payload: dict, signature: str, secret: str) -> bool:
    expected = sign_webhook_payload(payload, secret)
    return hmac.compare_digest(signature, expected)


def generate_api_key() -> str:
    return f"ihk_{uuid.uuid4().hex}{uuid.uuid4().hex[:16]}"


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_presigned_url(file_path: str, expiry_minutes: int | None = None) -> str:
    exp = expiry_minutes or settings.presigned_url_expiry_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "file": file_path,
        "iat": now,
        "exp": now + timedelta(minutes=exp),
        "purpose": "file_upload",
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
