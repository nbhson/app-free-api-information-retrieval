"""
Checker - Kiểm tra endpoint của provider có hoạt động không.

Có concurrency limit (semaphore) và retry với exponential backoff.
"""

import asyncio
import httpx
from datetime import datetime, timezone

from src.models import Provider, ProviderStatus

# Giới hạn số request song song — tránh trigger rate limit hàng loạt
MAX_CONCURRENCY = 5

# Retry cho lỗi tạm thời (timeout, connect error)
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 1.0  # giây — backoff = base * 2^attempt

_HEADERS = {"User-Agent": "free-llm-provider-discovery/1.0"}

# Semaphore dùng chung toàn process
_semaphore = asyncio.Semaphore(MAX_CONCURRENCY)


def _models_url(base_url: str) -> str:
    """Chuẩn hoá URL tới endpoint /models."""
    if not base_url.endswith("/models"):
        return base_url.rstrip("/") + "/models"
    return base_url


async def verify_provider(provider: Provider, timeout: float = 10.0,
                          retries: int = MAX_RETRIES) -> Provider:
    """
    Kiểm tra một provider có hoạt động không.
    Gửi GET request nhẹ tới {base_url}/models, retry khi lỗi tạm thời.
    """
    url = _models_url(provider.base_url)
    last_exc: Exception | None = None

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for attempt in range(retries + 1):
            try:
                async with _semaphore:
                    resp = await client.get(url, headers=_HEADERS)

                if resp.status_code == 200:
                    provider.status = ProviderStatus.ACTIVE
                elif resp.status_code == 401:
                    # Endpoint tồn tại nhưng cần auth -> vẫn coi là active
                    provider.status = ProviderStatus.ACTIVE
                elif resp.status_code == 429:
                    provider.status = ProviderStatus.RATE_LIMITED
                else:
                    provider.status = ProviderStatus.INACTIVE
                provider.last_verified = datetime.now(timezone.utc)
                return provider

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < retries:
                    # Exponential backoff, không chiếm semaphore khi chờ
                    await asyncio.sleep(RETRY_BACKOFF_BASE * (2 ** attempt))

            except Exception:
                provider.status = ProviderStatus.UNKNOWN
                provider.last_verified = datetime.now(timezone.utc)
                return provider

    provider.status = ProviderStatus.INACTIVE
    provider.last_verified = datetime.now(timezone.utc)
    return provider


async def verify_all_providers(providers: list[Provider]) -> list[Provider]:
    """Kiểm tra song song nhiều provider (giới hạn bởi MAX_CONCURRENCY)."""
    tasks = [verify_provider(p) for p in providers]
    return await asyncio.gather(*tasks)
