"""
REST API — Query provider data từ app khác.

Chạy server:
    python run.py serve --host 0.0.0.0 --port 8000

Endpoints:
    GET /                                  — thông tin API
    GET /api/v1/providers                  — danh sách provider (lọc + pagination)
    GET /api/v1/providers/{name}           — chi tiết 1 provider
    GET /api/v1/providers/{name}/history   — lịch sử verify + uptime%
    GET /api/v1/health                     — health report (registry + config)
    GET /api/v1/version                    — version API

Auth (optional): nếu env API_KEYS được set (comma-separated) thì mọi endpoint
data yêu cầu header X-API-Key; không set thì API public như cũ.
CORS: env CORS_ORIGINS (comma-separated) — rỗng = không bật CORS middleware.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from src.__version__ import __version__
from src.config import get_ai_config, get_api_config
from src.discovery import KNOWN_PROVIDERS, get_provider_by_name, get_providers_by_tag
from src.models import ProviderStatus
from src.storage.history import HistoryStore

# Các path public — không cần API key kể cả khi API_KEYS được set
_PUBLIC_PATHS = {"/", "/docs", "/redoc", "/openapi.json", "/api/v1/health", "/api/v1/version"}

app = FastAPI(
    title="Free LLM Provider Discovery API",
    description="REST API để tra cứu danh sách LLM API provider miễn phí",
    version=__version__,
)


@app.middleware("http")
async def api_key_auth_middleware(request: Request, call_next: Any) -> Any:
    """
    API key auth optional: chỉ bật khi env API_KEYS có giá trị.

    - API_KEYS="" (default) → public như cũ.
    - API_KEYS="k1,k2" → mọi path trừ _PUBLIC_PATHS yêu cầu header X-API-Key.
    """
    keys = get_api_config().get_api_keys()
    if keys and request.url.path not in _PUBLIC_PATHS:
        provided = request.headers.get("X-API-Key", "")
        if provided not in keys:
            return JSONResponse(
                status_code=401,
                content={"detail": "Thiếu hoặc sai API key. Truyền header 'X-API-Key'."},
            )
    return await call_next(request)


# CORS chỉ bật khi env CORS_ORIGINS được set (comma-separated origins)
_cors_origins = get_api_config().get_cors_origins()
if _cors_origins:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
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
            "GET /api/v1/providers?tag=free-tier&no_auth=false&free_only=true&limit=100&offset=0",
            "GET /api/v1/providers/{name}",
            "GET /api/v1/providers/{name}/history",
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
    limit: int = Query(
        100, ge=1, le=100, description="Số provider tối đa mỗi trang (max 100)"
    ),
    offset: int = Query(0, ge=0, description="Số provider bỏ qua (phân trang)"),
) -> dict[str, Any]:
    """Danh sách provider, hỗ trợ lọc theo tag / auth / free + pagination."""
    providers = list(KNOWN_PROVIDERS)
    if tag:
        providers = [p for p in providers if tag in p.tags]
    if no_auth:
        providers = [p for p in providers if not p.auth_required]

    total = len(providers)
    page = providers[offset : offset + limit]

    return {
        "total_count": total,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "meta": {
            "total": total,
            "count": len(page),
            "limit": limit,
            "offset": offset,
            "pages": math.ceil(total / limit) if total else 0,
        },
        "providers": [_provider_payload(p, include_paid_models=not free_only) for p in page],
    }


@app.get("/api/v1/providers/{name}/history")
def get_provider_history(
    name: str,
    limit: int = Query(50, ge=1, le=500, description="Số snapshot tối đa trả về"),
) -> dict[str, Any]:
    """
    Lịch sử verify của provider + uptime% (số lần ACTIVE / tổng số lần check).

    Dữ liệu từ SQLite (mặc định data/providers.db) — được ghi mỗi lần
    CLI `check` / `update` verify provider.
    """
    provider = get_provider_by_name(name)
    if provider is None:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{name}' không tồn tại. Xem danh sách: GET /api/v1/providers",
        )

    store = HistoryStore()
    history = store.get_history(name, limit=limit)
    uptime = store.get_uptime(name)

    return {
        "provider": provider.name,
        "uptime_percent": uptime["uptime_percent"],
        "total_checks": uptime["total_checks"],
        "active_count": uptime["active_count"],
        "history": [
            {
                "status": rec.status,
                "latency_ms": rec.latency_ms,
                "checked_at": rec.checked_at,
                "models_count": rec.models_count,
                "error": rec.error,
            }
            for rec in history
        ],
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
