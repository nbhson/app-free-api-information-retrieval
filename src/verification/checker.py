"""
Checker - Kiểm tra endpoint của provider có hoạt động không.

Có concurrency limit (semaphore) và retry với exponential backoff.
"""

import asyncio
from datetime import datetime, timezone

import httpx

from src.models import Provider, ProviderStatus

# Giới hạn số request song song — tránh trigger rate limit hàng loạt
MAX_CONCURRENCY = 5

# Retry cho lỗi tạm thời (timeout, connect error)
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 1.0  # giây — backoff = base * 2^attempt

_HEADERS = {"User-Agent": "free-llm-provider-discovery/1.0"}


def _models_url(base_url: str) -> str:
    """Chuẩn hoá URL tới endpoint /models."""
    if not base_url.endswith("/models"):
        return base_url.rstrip("/") + "/models"
    return base_url


async def verify_provider(
    provider: Provider, timeout: float = 10.0, retries: int = MAX_RETRIES
) -> Provider:
    """
    Kiểm tra một provider có hoạt động không.
    Gửi GET request nhẹ tới {base_url}/models, retry khi lỗi tạm thời.
    Trả về bản copy — không mutate provider gốc.
    """
    # Tạo bản copy để không mutate shared state (singleton trong KNOWN_PROVIDERS)
    result = provider.model_copy(deep=True)
    url = _models_url(result.base_url)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for attempt in range(retries + 1):
            try:
                resp = await client.get(url, headers=_HEADERS)

                if resp.status_code == 200:
                    result.status = ProviderStatus.ACTIVE
                elif resp.status_code == 401:
                    # Endpoint tồn tại nhưng cần auth -> vẫn coi là active
                    result.status = ProviderStatus.ACTIVE
                elif resp.status_code == 429:
                    result.status = ProviderStatus.RATE_LIMITED
                else:
                    result.status = ProviderStatus.INACTIVE
                result.last_verified = datetime.now(timezone.utc)
                return result

            except (httpx.ConnectError, httpx.TimeoutException):
                if attempt < retries:
                    # Exponential backoff, không chiếm semaphore khi chờ
                    await asyncio.sleep(RETRY_BACKOFF_BASE * (2**attempt))

            except Exception:
                result.status = ProviderStatus.UNKNOWN
                result.last_verified = datetime.now(timezone.utc)
                return result

    result.status = ProviderStatus.INACTIVE
    result.last_verified = datetime.now(timezone.utc)
    return result


async def verify_all_providers(providers: list[Provider]) -> list[Provider]:
    """Kiểm tra song song nhiều provider (giới hạn bởi MAX_CONCURRENCY)."""
    # Semaphore cục bộ cho mỗi lần gọi — tránh lỗi event loop khi dùng lại ở event loop khác
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def bounded(p: Provider) -> Provider:
        async with semaphore:
            return await verify_provider(p)

    tasks = [bounded(p) for p in providers]
    return await asyncio.gather(*tasks)
