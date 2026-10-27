"""
Checker - Kiểm tra endpoint của provider có hoạt động không
"""

import httpx
from typing import Optional
from datetime import datetime
from src.models import Provider, ProviderStatus


async def verify_provider(provider: Provider, timeout: float = 10.0) -> Provider:
    """
    Kiểm tra một provider có hoạt động không.
    Gửi GET request nhẹ tới base_url để xem có phản hồi không.
    """
    headers = {"User-Agent": "free-llm-provider-discovery/1.0"}
    if provider.base_url.endswith("/models") is False:
        url = provider.base_url.rstrip("/") + "/models"
    else:
        url = provider.base_url

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                provider.status = ProviderStatus.ACTIVE
            elif resp.status_code == 401:
                # Endpoint tồn tại nhưng cần auth -> vẫn coi là active
                provider.status = ProviderStatus.ACTIVE
            elif resp.status_code == 429:
                provider.status = ProviderStatus.RATE_LIMITED
            else:
                provider.status = ProviderStatus.INACTIVE
            provider.last_verified = datetime.utcnow()
    except (httpx.ConnectError, httpx.TimeoutException):
        provider.status = ProviderStatus.INACTIVE
        provider.last_verified = datetime.utcnow()
    except Exception:
        provider.status = ProviderStatus.UNKNOWN
        provider.last_verified = datetime.utcnow()

    return provider


async def verify_all_providers(providers: list[Provider]) -> list[Provider]:
    """Kiểm tra song song nhiều provider"""
    import asyncio
    tasks = [verify_provider(p) for p in providers]
    return await asyncio.gather(*tasks)
