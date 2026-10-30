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


class WebhookConfig(BaseSettings):
    """Cấu hình webhook notification khi provider status thay đổi."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = Field("", alias="WEBHOOK_URL")
    timeout: int = Field(10, alias="WEBHOOK_TIMEOUT")
    enabled: bool = Field(True, alias="WEBHOOK_ENABLED")

    @field_validator("timeout")
    @classmethod
    def _validate_timeout(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("WEBHOOK_TIMEOUT phải > 0")
        return v

    def is_configured(self) -> bool:
        """Webhook sẵn sàng = có URL và được bật."""
        return bool(self.url) and self.enabled

    def validation_errors(self) -> list[str]:
        """Validate config, trả về list lỗi (rỗng = OK)."""
        errors: list[str] = []
        if self.url and not self.url.startswith(("http://", "https://")):
            errors.append("WEBHOOK_URL phải bắt đầu bằng http:// hoặc https://")
        if self.timeout <= 0:
            errors.append("WEBHOOK_TIMEOUT phải > 0")
        return errors


class APIConfig(BaseSettings):
    """Cấu hình REST API: API key auth (optional) + CORS."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Comma-separated danh sách API key hợp lệ. Rỗng = API public (không auth).
    # VD: API_KEYS="key1,key2,key3"
    api_keys: str = Field("", alias="API_KEYS")
    # Comma-separated danh sách origin được phép CORS. Rỗng = không bật CORS middleware.
    # VD: CORS_ORIGINS="https://app.example.com,https://admin.example.com"
    cors_origins: str = Field("", alias="CORS_ORIGINS")

    def get_api_keys(self) -> set[str]:
        """Parse danh sách API key hợp lệ từ env (comma-separated)."""
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    def get_cors_origins(self) -> list[str]:
        """Parse danh sách origin được phép CORS từ env (comma-separated)."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def is_auth_enabled(self) -> bool:
        """Auth chỉ bật khi có ít nhất 1 API key."""
        return bool(self.get_api_keys())


class GoogleSearchConfig(BaseSettings):
    """
    Cấu hình Google Custom Search API cho backend 'google' (discover-web).

    - Có đủ GOOGLE_API_KEY + GOOGLE_CSE_ID → dùng Custom Search JSON API
      (web index THẬT của Google, kết quả đáng tin nhất).
    - Thiếu 1 trong 2 → backend tự fallback sang Google News RSS (public,
      không cần key) — vẫn chạy được nhưng chỉ phủ trang tin tức.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str = Field("", alias="GOOGLE_API_KEY")
    cse_id: str = Field("", alias="GOOGLE_CSE_ID")

    def is_configured(self) -> bool:
        """Custom Search API sẵn sàng = có đủ key + CSE ID."""
        return bool(self.api_key and self.cse_id)


class StorageConfig(BaseSettings):
    """Cấu hình storage cho lịch sử verify (SQLite)."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Đường dẫn SQLite DB lưu lịch sử verify. Default: data/providers.db
    db_path: Path = Field(Path("data") / "providers.db", alias="HISTORY_DB_PATH")


@lru_cache(maxsize=1)
def get_ai_config() -> AIConfig:
    """Singleton config — cache để env thay đổi sau import vẫn nhất quán."""
    return AIConfig()


@lru_cache(maxsize=1)
def get_webhook_config() -> WebhookConfig:
    """Singleton webhook config — cache để env thay đổi sau import vẫn nhất quán."""
    return WebhookConfig()


@lru_cache(maxsize=1)
def get_api_config() -> APIConfig:
    """Singleton API config (auth keys + CORS)."""
    return APIConfig()


@lru_cache(maxsize=1)
def get_google_config() -> GoogleSearchConfig:
    """Singleton Google Custom Search config (backend 'google' của discover-web)."""
    return GoogleSearchConfig()


@lru_cache(maxsize=1)
def get_storage_config() -> StorageConfig:
    """Singleton storage config (DB path cho lịch sử verify)."""
    return StorageConfig()
