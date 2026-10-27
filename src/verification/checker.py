"""
Checker - Kiểm tra endpoint của provider có hoạt động không.

Có concurrency limit (semaphore) và retry với exponential backoff cho:
- Timeout / ConnectError: retry ngay lập tức với backoff
- HTTP 429 (rate limit): retry với backoff
- HTTP 5xx: retry với backoff
- Các lỗi khác: log và trả về UNKNOWN
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from src.__version__ import __version__
from src.models import Provider, ProviderStatus

logger = logging.getLogger(__name__)

# Giới hạn số request song song — tránh trigger rate limit hàng loạt
MAX_CONCURRENCY = 5

# Retry cho lỗi tạm thời (timeout, connect, 429, 5xx)
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 1.0  # giây — backoff = base * 2^attempt

_HEADERS = {"User-Agent": f"free-llm-provider-discovery/{__version__}"}


def _models_url(base_url: str) -> str:
    """Chuẩn hoá URL tới endpoint /models."""
    if not base_url.endswith("/models"):
        return base_url.rstrip("/") + "/models"
    return base_url


def _should_retry_status(status_code: int) -> bool:
    """True nếu status code là lỗi tạm thời có thể retry."""
    return status_code in (429, 500, 502, 503, 504)


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
                elif _should_retry_status(resp.status_code):
                    # 429 / 5xx — retry với backoff; hết lượt thì đánh dấu kết quả cuối
                    if attempt < retries:
                        backoff = RETRY_BACKOFF_BASE * (2**attempt)
                        logger.debug(
                            "HTTP %s from %s (attempt %d), retrying in %.1fs",
                            resp.status_code,
                            url,
                            attempt + 1,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    result.status = (
                        ProviderStatus.RATE_LIMITED
                        if resp.status_code == 429
                        else ProviderStatus.INACTIVE
                    )
                else:
                    result.status = ProviderStatus.INACTIVE

                result.last_verified = datetime.now(timezone.utc)
                return result

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < retries:
                    backoff = RETRY_BACKOFF_BASE * (2**attempt)
                    logger.debug(
                        "%s from %s (attempt %d), retrying in %.1fs",
                        type(e).__name__,
                        url,
                        attempt + 1,
                        backoff,
                    )
                    await asyncio.sleep(backoff)

            except httpx.HTTPError as e:
                # Các lỗi HTTP khác (invalid URL, proxy, etc.) → UNKNOWN
                logger.warning("Lỗi HTTP không xác định khi kiểm tra %s: %s", url, e)
                result.status = ProviderStatus.UNKNOWN
                result.last_verified = datetime.now(timezone.utc)
                return result

            except Exception as e:
                # Safety net: mọi lỗi không lường trước → UNKNOWN, không crash cả batch
                logger.warning("Lỗi không mong muốn khi kiểm tra %s: %r", url, e)
                result.status = ProviderStatus.UNKNOWN
                result.last_verified = datetime.now(timezone.utc)
                return result

        # Fallback cuối cùng (sau khi đã retry hết)
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
