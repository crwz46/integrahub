from typing import Any

from app.adapters.base import BaseATSAdapter
from app.adapters.greenhouse import GreenhouseAdapter
from app.adapters.workday import WorkdayAdapter


class AdapterRegistry:
    _adapters: dict[str, type[BaseATSAdapter]] = {
        "workday": WorkdayAdapter,
        "greenhouse": GreenhouseAdapter,
    }

    @classmethod
    def get(cls, provider: str, config: dict | None = None) -> BaseATSAdapter:
        adapter_cls = cls._adapters.get(provider)
        if not adapter_cls:
            raise ValueError(f"Unsupported provider: {provider}. Available: {list(cls._adapters.keys())}")
        return adapter_cls(config)

    @classmethod
    def list_providers(cls) -> list[dict[str, Any]]:
        return [
            {"provider": "workday", "name": WorkdayAdapter.name, "version": "v1"},
            {"provider": "greenhouse", "name": GreenhouseAdapter.name, "version": "v1"},
            {"provider": "lever", "name": "Lever", "version": "v1"},
            {"provider": "icims", "name": "iCIMS", "version": "v1"},
            {"provider": "custom", "name": "Custom API", "version": "v1"},
        ]


__all__ = ["BaseATSAdapter", "AdapterRegistry", "WorkdayAdapter", "GreenhouseAdapter"]
