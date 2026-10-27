"""
Cấu hình ứng dụng — dùng Pydantic Settings (chuẩn enterprise).

Load từ .env / environment variables, có validation và type-safety.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Đường dẫn .env ở thư mục gốc project
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class AIConfig(BaseSettings):
    """Cấu hình AI provider cho discovery."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = Field("", alias="AI_PROVIDER_BASE_URL")
    api_key: str = Field("", alias="AI_API_KEY")
    model: str = Field("openai/gpt-4o-mini", alias="AI_MODEL")
    timeout: int = Field(60, alias="AI_TIMEOUT")

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: str) -> str:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("AI_PROVIDER_BASE_URL phải bắt đầu bằng http:// hoặc https://")
        return v.rstrip("/")

    @field_validator("timeout")
    @classmethod
    def _validate_timeout(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("AI_TIMEOUT phải > 0")
        return v

    def is_configured(self) -> bool:
        """Kiểm tra đã có đủ config chưa."""
        return bool(self.base_url and self.api_key and self.model)

    def validation_errors(self) -> list[str]:
        """Validate config, trả về list lỗi (rỗng = OK)."""
        errors: list[str] = []
        if not self.base_url:
            errors.append("AI_PROVIDER_BASE_URL chưa được set")
        if not self.api_key:
            errors.append("AI_API_KEY chưa được set")
        if not self.model:
            errors.append("AI_MODEL chưa được set")
        if self.timeout <= 0:
            errors.append("AI_TIMEOUT phải > 0")
        return errors


@lru_cache(maxsize=1)
def get_ai_config() -> AIConfig:
    """Singleton config — cache để env thay đổi sau import vẫn nhất quán."""
    return AIConfig()
