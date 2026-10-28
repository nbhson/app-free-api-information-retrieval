"""
REST API — Query provider data từ app khác.

Chạy server:
    python run.py serve --host 0.0.0.0 --port 8000

Endpoints:
    GET /                         — thông tin API
    GET /api/v1/providers         — danh sách provider (lọc theo tag, auth, free)
    GET /api/v1/providers/{name}  — chi tiết 1 provider
    GET /api/v1/health            — health report (registry + config)
    GET /api/v1/version           — version API
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from src.__version__ import __version__
from src.config import get_ai_config
from src.discovery import KNOWN_PROVIDERS, get_provider_by_name, get_providers_by_tag
from src.models import ProviderStatus

app = FastAPI(
    title="Free LLM Provider Discovery API",
    description="REST API để tra cứu danh sách LLM API provider miễn phí",
    version=__version__,
)


def _provider_payload(p, include_paid_models: bool = False) -> dict[str, Any]:
    """Serialize provider ra dict — mặc định chỉ gồm models free."""
    data = p.model_dump(mode="json")
    if not include_paid_models:
        data["models"] = [m for m in data["models"] if m["is_free"]]
    return data


@app.get("/")
def root() -> dict[str, Any]:
    """Thông tin tổng quan về API."""
    return {
        "name": "Free LLM Provider Discovery API",
        "version": __version__,
        "docs": "/docs",
        "endpoints": [
            "GET /api/v1/providers?tag=free-tier&no_auth=false&free_only=true",
            "GET /api/v1/providers/{name}",
            "GET /api/v1/health",
            "GET /api/v1/version",
        ],
    }


@app.get("/api/v1/version")
def get_version() -> dict[str, str]:
    """Version của API."""
    return {"version": __version__}


@app.get("/api/v1/providers")
def list_providers(
    tag: str | None = Query(None, description="Lọc theo tag (vd: free-tier)"),
    no_auth: bool = Query(False, description="Chỉ provider không cần API key"),
    free_only: bool = Query(True, description="Chỉ trả về models free"),
) -> dict[str, Any]:
    """Danh sách provider, hỗ trợ lọc theo tag / auth / free."""
    providers = list(KNOWN_PROVIDERS)
    if tag:
        providers = [p for p in providers if tag in p.tags]
    if no_auth:
        providers = [p for p in providers if not p.auth_required]

    return {
        "total_count": len(providers),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "providers": [_provider_payload(p, include_paid_models=not free_only) for p in providers],
    }


@app.get("/api/v1/providers/{name}")
def get_provider_detail(name: str) -> dict[str, Any]:
    """Chi tiết 1 provider theo tên (không phân biệt hoa thường). 404 nếu không có."""
    p = get_provider_by_name(name)
    if p is None:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{name}' không tồn tại. Xem danh sách: GET /api/v1/providers",
        )
    return _provider_payload(p, include_paid_models=True)


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    """Health report: registry stats + config + API status."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "registry": {
            "total_providers": len(KNOWN_PROVIDERS),
            "free_tier_count": len(get_providers_by_tag("free-tier")),
            "verified_count": len(
                [p for p in KNOWN_PROVIDERS if p.status == ProviderStatus.ACTIVE]
            ),
        },
        "ai_configured": get_ai_config().is_configured(),
        "version": __version__,
    }
