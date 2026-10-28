"""
Webhook Notification — POST payload JSON khi provider status thay đổi.

Cấu hình qua .env (xem .env.example):
    WEBHOOK_URL=https://hooks.example.com/xyz   # trống = tắt thông báo
    WEBHOOK_TIMEOUT=10                          # giây
    WEBHOOK_ENABLED=true

Thiết kế an toàn: notification KHÔNG BAO GIỜ làm crash pipeline verify —
mọi lỗi network/logic chỉ được log warning.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel, Field

from src.__version__ import __version__
from src.config import WebhookConfig
from src.models import Provider

logger = logging.getLogger(__name__)


class StatusChange(BaseModel):
    """Một lần thay đổi status của provider sau khi verify."""

    provider: str = Field(..., description="Tên provider")
    base_url: str = Field(..., description="Base URL của provider")
    old_status: str = Field(..., description="Status trước khi verify (registry)")
    new_status: str = Field(..., description="Status sau khi verify")


def detect_status_changes(
    originals: list[Provider], verified: list[Provider]
) -> list[StatusChange]:
    """
    So sánh status registry gốc với kết quả verify (theo tên provider).

    Provider mới xuất hiện sau verify (không có trong originals) có
    old_status = "unknown".
    """
    old_by_name = {p.name: p.status.value for p in originals}
    changes: list[StatusChange] = []
    for p in verified:
        old = old_by_name.get(p.name, "unknown")
        if old != p.status.value:
            changes.append(
                StatusChange(
                    provider=p.name,
                    base_url=p.base_url,
                    old_status=old,
                    new_status=p.status.value,
                )
            )
    return changes


def build_payload(changes: list[StatusChange]) -> dict:
    """Payload JSON chuẩn gửi tới webhook."""
    return {
        "event": "provider_status_changed",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_changes": len(changes),
        "changes": [c.model_dump(mode="json") for c in changes],
    }


def send_webhook_notification(
    changes: list[StatusChange],
    config: WebhookConfig,
) -> bool:
    """
    Gửi notification tới webhook URL. Fire-and-forget an toàn:
    trả về True nếu deliver thành công, False nếu lỗi/chưa cấu hình/không có change.
    Không bao giờ raise.
    """
    if not changes:
        return False
    if not config.is_configured():
        logger.debug("Webhook chưa cấu hình (WEBHOOK_URL trống hoặc WEBHOOK_ENABLED=false)")
        return False

    try:
        resp = httpx.post(
            config.url,
            json=build_payload(changes),
            timeout=float(config.timeout),
            headers={
                "User-Agent": f"free-llm-provider-discovery/{__version__}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code >= 400:
            logger.warning(
                "Webhook trả về HTTP %s — notification có thể không được xử lý",
                resp.status_code,
            )
            return False
        return True
    except httpx.HTTPError as e:
        logger.warning("Lỗi network khi gửi webhook tới %s: %s", config.url, e)
        return False
    except Exception as e:  # noqa: BLE001 — safety net, notification không được crash pipeline
        logger.warning("Lỗi không mong muốn khi gửi webhook: %r", e)
        return False
