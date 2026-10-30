"""
AI Discovery Agent - Dùng LLM để tìm kiếm provider LLM miễn phí mới
"""

import json
import re
import time

import httpx

from src.config import AIConfig, get_ai_config
from src.logging_config import get_logger
from src.models import APIStyle, AuthType, Model, Provider, ProviderStatus

logger = get_logger(__name__)

# Backoff giữa các lần retry 429/5xx — cùng convention với checker.py / live.py
RETRY_BACKOFF_BASE = 1.0  # giây — backoff = base * 2^attempt

SYSTEM_PROMPT = """Bạn là một chuyên gia nghiên cứu về các LLM API providers.
Nhiệm vụ: tìm kiếm và liệt kê các nhà cung cấp API LLM MIỄN PHÍ (free tier) hiện có.

Chỉ trả về JSON thuần (không markdown, không giải thích), theo schema:

{
  "providers": [
    {
      "name": "Tên provider",
      "base_url": "https://... (endpoint API chính thức)",
      "website": "https://... (trang chủ)",
      "description": "Mô tả ngắn",
      "api_style": "openai | anthropic | custom",
      "auth_required": true/false,
      "rate_limit": "mô tả giới hạn free tier",
      "tags": ["tag1", "tag2"],
      "free_models": [
        {"id": "model-id", "name": "Tên model", "context_length": 8192}
      ]
    }
  ]
}

Lưu ý:
- Chỉ liệt kê provider THỰC SỰ tồn tại và có free tier, không bịa.
- base_url phải là endpoint API thật (ưu tiên OpenAI-compatible /v1).
- free_models chỉ chứa model miễn phí thật sự.
- Trả về 5-15 provider đáng tin cậy nhất."""


def _extract_json(text: str) -> dict:
    """Trích xuất JSON từ response của LLM (xử lý cả markdown fence và brace trong string)."""
    # Bỏ markdown code fence nếu có
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    # Tìm object JSON đầu tiên và dùng json.JSONDecoder.raw_decode
    # để parse chính xác ngay cả khi value chứa ký tự { } bên trong chuỗi
    brace_start = text.find("{")
    if brace_start == -1:
        raise ValueError("Không tìm thấy JSON trong response của AI")

    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(text[brace_start:])
        if not isinstance(obj, dict):
            raise ValueError(f"JSON parse ra {type(obj).__name__}, kỳ vọng object/dict")
        return obj
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON không hợp lệ: {e}") from e


def _parse_providers(data: dict) -> list[Provider]:
    """Mapping JSON từ AI sang list Provider."""
    providers = []
    for entry in data.get("providers", []):
        try:
            models = []
            for m in entry.get("free_models", []):
                models.append(
                    Model(
                        id=m.get("id", "unknown"),
                        name=m.get("name", m.get("id", "unknown")),
                        is_free=True,
                        context_length=m.get("context_length"),
                    )
                )

            api_style_raw = str(entry.get("api_style", "openai")).lower()
            try:
                api_style = APIStyle(api_style_raw)
            except ValueError:
                api_style = APIStyle.CUSTOM

            auth_raw = entry.get("auth_required", True)
            if isinstance(auth_raw, str):
                auth_required = auth_raw.lower() in ("true", "yes", "1")
            else:
                auth_required = bool(auth_raw)

            providers.append(
                Provider(
                    name=entry.get("name", "Unknown"),
                    base_url=str(entry.get("base_url", "")).rstrip("/"),
                    website=entry.get("website"),
                    description=entry.get("description"),
                    models=models,
                    status=ProviderStatus.UNKNOWN,
                    auth_type=AuthType.NONE if not auth_required else AuthType.API_KEY,
                    api_style=api_style,
                    auth_required=auth_required,
                    rate_limit=entry.get("rate_limit"),
                    tags=list(entry.get("tags", [])) + ["ai-discovered"],
                )
            )
        except Exception as e:
            logger.warning("Bỏ qua entry lỗi khi parse AI response: %s", e)
    return providers


class AIDiscoveryError(Exception):
    """Lỗi khi chạy AI discovery."""


def discover_with_ai(config: AIConfig | None = None, max_retries: int = 2) -> list[Provider]:
    """
    Gọi LLM để tìm kiếm provider miễn phí mới.

    Raises:
        AIDiscoveryError: khi config thiếu, API lỗi, hoặc response sai schema.
    """
    config = config or get_ai_config()
    errors = config.validation_errors()
    if errors:
        raise AIDiscoveryError(
            "Chưa cấu hình AI provider. Tạo file .env từ .env.example:\n  " + "\n  ".join(errors)
        )

    base_url = config.base_url.rstrip("/")
    url = f"{base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Hãy liệt kê các LLM API provider miễn phí hiện có trên internet. "
                "Chỉ trả về JSON theo schema đã cho.",
            },
        ],
        "temperature": 0.2,
    }

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=config.timeout)
            if resp.status_code == 401:
                raise AIDiscoveryError("API key sai hoặc hết hạn (HTTP 401)")
            if resp.status_code == 403:
                raise AIDiscoveryError("Không có quyền truy cập (HTTP 403)")
            # 429/5xx là lỗi tạm thời — retry với backoff thay vì raise ngay
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = (
                    f"HTTP {resp.status_code} từ {url} (lỗi tạm thời)"
                    if resp.status_code == 429
                    else f"HTTP {resp.status_code} (server error) từ {url}"
                )
                if attempt < max_retries:
                    logger.warning(
                        "Lần %d lỗi: %s. Thử lại sau backoff...", attempt + 1, last_error
                    )
                    # Backoff trước khi retry — không đánh nhau với server đang rate limit
                    time.sleep(RETRY_BACKOFF_BASE * (2**attempt))
                    continue
                raise AIDiscoveryError(last_error)
            resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = _extract_json(content)
            return _parse_providers(parsed)

        except AIDiscoveryError:
            raise
        except httpx.TimeoutException:
            last_error = f"Timeout sau {config.timeout}s khi gọi {url}"
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code} từ {url}"
        except (KeyError, IndexError):
            last_error = "Response của AI không đúng cấu trúc (thiếu choices/message/content)"
        except json.JSONDecodeError as e:
            last_error = f"AI trả về JSON không hợp lệ: {e}"
        except ValueError as e:
            last_error = str(e)

        if attempt < max_retries:
            logger.warning("Lần %d lỗi: %s. Thử lại sau backoff...", attempt + 1, last_error)
            time.sleep(RETRY_BACKOFF_BASE * (2**attempt))

    raise AIDiscoveryError(last_error or "Không rõ lỗi")
