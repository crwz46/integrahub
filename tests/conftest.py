from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def clean_data():
    """Clean all persisted test data before each test."""
    base = Path(__file__).resolve().parent.parent / "data"
    for subdir in ["integrations", "jobs", "queue", "webhooks", "reports", "uploads"]:
        path = base / subdir
        if path.exists():
            for f in path.glob("*.json"):
                f.unlink()
    # Reset in-memory stores
    from app.main import api_keys_store
    api_keys_store.clear()
    yield
