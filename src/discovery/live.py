"""
Live Discovery — Tìm model free từ dữ liệu internet THẬT.

Không phụ thuộc trí nhớ LLM hay registry cứng: query trực tiếp API công khai
của OpenRouter (/models, không cần API key), lọc model có pricing = $0.
Dữ liệu trả về là trạng thái THỜI ĐIỂM GỌI — luôn mới hơn registry cứng.
"""

import httpx
from rich.console import Console

from src.models import APIStyle, AuthType, Model, Provider, ProviderStatus

console = Console()

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

_HEADERS = {"User-Agent": "free-llm-provider-discovery/1.1"}


class LiveDiscoveryError(Exception):
    """Lỗi khi chạy live discovery."""


def _is_free(pricing: dict) -> bool:
    """Model free = prompt VÀ completion đều có giá 0 (string '0')."""
    return pricing.get("prompt") == "0" and pricing.get("completion") == "0"


def _parse_free_models(data: dict) -> list[Model]:
    """Trích xuất models free từ payload /models của OpenRouter."""
    models: list[Model] = []
    for entry in data.get("data", []):
        pricing = entry.get("pricing") or {}
        if not _is_free(pricing):
            continue
        models.append(
            Model(
                id=entry.get("id", "unknown"),
                name=entry.get("name") or entry.get("id", "unknown"),
                is_free=True,
                context_length=entry.get("context_length"),
                supports_streaming=True,
                description=entry.get("description"),
            )
        )
    return models


def fetch_openrouter_free_models(
    timeout: float = 15.0, base_url: str = OPENROUTER_MODELS_URL
) -> list[Model]:
    """
    Gọi OpenRouter /models (public, không cần key) và trả về models free thật.

    Raises:
        LiveDiscoveryError: khi network lỗi hoặc response sai schema.
    """
    try:
        resp = httpx.get(OPENROUTER_MODELS_URL, timeout=timeout, headers=_HEADERS)
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException as e:
        raise LiveDiscoveryError(f"Timeout sau {timeout}s khi gọi {OPENROUTER_MODELS_URL}") from e
    except httpx.HTTPStatusError as e:
        raise LiveDiscoveryError(f"HTTP {e.response.status_code} từ {OPENROUTER_MODELS_URL}") from e
    except (httpx.HTTPError, ValueError) as e:
        raise LiveDiscoveryError(f"Lỗi khi gọi {OPENROUTER_MODELS_URL}: {e}") from e

    try:
        return _parse_free_models(data)
    except (AttributeError, TypeError) as e:
        raise LiveDiscoveryError(f"Response của OpenRouter không đúng cấu trúc: {e}") from e


def build_openrouter_live_provider(models: list[Model]) -> Provider:
    """Tạo Provider OpenRouter với models free LẤY TỪ API LIVE."""
    return Provider(
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        website="https://openrouter.ai",
        description=(
            f"Live discovery từ API: {len(models)} model free thực tế "
            f"(pricing prompt=0, completion=0)."
        ),
        models=models,
        status=ProviderStatus.ACTIVE,
        auth_type=AuthType.API_KEY,
        api_style=APIStyle.OPENAI,
        auth_required=True,
        rate_limit="Free models: 50 req/ngày (không card); 1000 req/ngày (có card $10+)",
        tags=["aggregation", "multi-model", "popular", "free-tier", "live-discovered"],
    )


def discover_live() -> Provider:
    """
    Query dữ liệu THẬT từ internet (OpenRouter /models) và trả về
    Provider với danh sách model free hiện tại.

    Raises:
        LiveDiscoveryError: khi API lỗi hoặc response sai cấu trúc.
    """
    models = fetch_openrouter_free_models()
    if not models:
        raise LiveDiscoveryError(
            "OpenRouter không trả về model free nào (API có thể đã thay đổi schema pricing)"
        )
    return build_openrouter_live_provider(models)
