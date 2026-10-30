"""
Checker - Kiểm tra endpoint của provider có hoạt động không.

Có concurrency limit (semaphore) và retry với exponential backoff cho:
- Timeout / ConnectError: retry với backoff; hết lượt → UNKNOWN (không chắc endpoint chết)
- HTTP 429 (rate limit): retry với backoff, hết lượt → RATE_LIMITED
- HTTP 5xx: retry với backoff, hết lượt → INACTIVE
- Các lỗi khác: log và trả về UNKNOWN
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from src.__version__ import __version__
from src.models import Model, Provider, ProviderStatus

logger = logging.getLogger(__name__)

# Callback báo tiến độ: (completed, total, provider vừa verify xong)
ProgressCallback = Callable[[int, int, Provider], None]


class SmokeTestError(Exception):
    """Lỗi khi smoke test chat completion với provider thật."""


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


def _build_headers(api_key: str | None = None) -> dict[str, str]:
    """Headers cho request verify — thêm Authorization khi có API key."""
    headers = dict(_HEADERS)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _parse_models_payload(payload: object) -> list[Model]:
    """
    Parse JSON response của endpoint /models (chuẩn OpenAI) thành list[Model].

    Chấp nhận nhiều biến thể thực tế:
    - {"data": [{"id": "gpt-4", ...}, ...]}      (OpenAI chuẩn)
    - {"models": [{"id": ...} | "name-str", ...]} (một số provider tự chế)
    - ["model-a", "model-b"]                      (list string thuần)
    Model thiếu trường bắt buộc sẽ bị bỏ qua — không để 1 item lỗi làm chết cả list.
    """
    items: object = payload
    if isinstance(payload, dict):
        items = payload.get("data", payload.get("models", []))
    if not isinstance(items, (list, tuple)):
        return []

    models: list[Model] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            candidates = [{"id": item, "name": item}]
        elif isinstance(item, dict):
            # Một số provider dùng "name"/"model" thay vì "id"
            model_id = item.get("id") or item.get("name") or item.get("model")
            if not model_id:
                continue
            candidates = [{**item, "id": str(model_id), "name": str(item.get("name") or model_id)}]
        else:
            continue

        for cand in candidates:
            try:
                model = Model.model_validate(cand)
            except ValidationError:
                continue
            if model.id not in seen:
                seen.add(model.id)
                models.append(model)
    return models


async def verify_provider(
    provider: Provider,
    timeout: float = 10.0,
    retries: int = MAX_RETRIES,
    api_key: str | None = None,
    parse_models: bool = False,
) -> Provider:
    """
    Kiểm tra một provider có hoạt động không.
    Gửi GET request tới {base_url}/models, retry khi lỗi tạm thời.

    Args:
        api_key: Nếu set, gửi Authorization: Bearer — cho phép verify các endpoint
            yêu cầu auth mới phản hồi 200 (thay vì chỉ dựa vào 401).
        parse_models: Nếu True và response 200 + JSON hợp lệ, cập nhật danh sách
            model của provider từ dữ liệu thật trả về (thay cho danh sách tĩnh).

    Trả về bản copy — không mutate provider gốc.
    """
    # Tạo bản copy để không mutate shared state (singleton trong KNOWN_PROVIDERS)
    result = provider.model_copy(deep=True)
    url = _models_url(result.base_url)
    headers = _build_headers(api_key)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for attempt in range(retries + 1):
            try:
                resp = await client.get(url, headers=headers)

                if resp.status_code == 200:
                    result.status = ProviderStatus.ACTIVE
                    if parse_models:
                        try:
                            parsed = _parse_models_payload(resp.json())
                            if parsed:
                                result.models = parsed
                        except ValueError as e:
                            # Body không phải JSON hợp lệ — endpoint vẫn sống,
                            # chỉ không sync được model list.
                            logger.debug("Không parse được /models JSON từ %s: %s", url, e)
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

        # Fallback cuối cùng (sau khi đã retry hết): timeout/connect error
        # là lỗi phía mạng/ta — không chắc endpoint chết, đánh dấu UNKNOWN
        # (giữ INACTIVE cho các case khác: 5xx, 4xx sau retries).
        logger.warning("Provider %s không xác định được trạng thái sau retries", url)
        result.status = ProviderStatus.UNKNOWN
        result.last_verified = datetime.now(timezone.utc)
        return result


async def verify_all_providers(
    providers: list[Provider], progress_callback: ProgressCallback | None = None
) -> list[Provider]:
    """
    Kiểm tra song song nhiều provider (giới hạn bởi MAX_CONCURRENCY).

    Args:
        providers: Danh sách provider cần verify.
        progress_callback: Optional — được gọi sau mỗi provider hoàn tất
            với (completed, total, provider). Dùng để vẽ progress bar ở CLI.
    """
    # Semaphore cục bộ cho mỗi lần gọi — tránh lỗi event loop khi dùng lại ở event loop khác
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    total = len(providers)
    completed = 0

    async def bounded(p: Provider) -> Provider:
        nonlocal completed
        async with semaphore:
            result = await verify_provider(p)
            completed += 1
            if progress_callback is not None:
                progress_callback(completed, total, result)
            return result

    tasks = [bounded(p) for p in providers]
    return list(await asyncio.gather(*tasks))


# ─── Smoke test chat completion thật ───

_SMOKE_DEFAULT_PROMPT = "Reply with exactly: OK"
_SMOKE_MAX_TOKENS = 16


async def smoke_test_chat(
    provider: Provider,
    model_id: str,
    api_key: str | None = None,
    timeout: float = 30.0,
    prompt: str = _SMOKE_DEFAULT_PROMPT,
    max_tokens: int = _SMOKE_MAX_TOKENS,
) -> dict[str, Any]:
    """
    Gửi 1 chat completion THẬT tới provider để xác nhận model hoạt động end-to-end.

    Khác verify_provider (chỉ ping /models), smoke test chứng minh:
    - API key hợp lệ, model tồn tại, inference trả text được.

    Chỉ dùng với model nhẹ / max_tokens nhỏ để tiết kiệm quota.

    Returns:
        dict: {content, model, latency_ms, finish_reason, usage}

    Raises:
        SmokeTestError: khi HTTP lỗi, timeout, response sai chuẩn, hoặc content rỗng.
    """
    url = provider.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    headers = _build_headers(api_key)
    headers["Content-Type"] = "application/json"

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        raise SmokeTestError(f"Timeout/kết nối thất bại tới {url}: {e}") from e
    except httpx.HTTPError as e:
        raise SmokeTestError(f"Lỗi HTTP khi gọi {url}: {e}") from e

    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    if resp.status_code != 200:
        detail = ""
        try:
            detail = " " + str(resp.json().get("error", ""))[:300]
        except ValueError:
            detail = " " + resp.text[:300]
        raise SmokeTestError(f"HTTP {resp.status_code} từ {url} (model={model_id}):{detail}")

    try:
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        finish_reason = body["choices"][0].get("finish_reason")
        usage = body.get("usage", {})
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise SmokeTestError(
            f"Response chat completion không đúng chuẩn OpenAI từ {url}: {e}"
        ) from e

    if not content:
        raise SmokeTestError(f"Model {model_id} trả về content rỗng")

    return {
        "content": content,
        "model": model_id,
        "latency_ms": latency_ms,
        "finish_reason": finish_reason,
        "usage": usage,
    }
