from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

# ─── Load .env ───
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
else:
    import os
    os.environ.setdefault("AI_PROVIDER_BASE_URL", "")
    os.environ.setdefault("AI_API_KEY", "")
    os.environ.setdefault("AI_MODEL", "openai/gpt-4o-mini")
    os.environ.setdefault("AI_TIMEOUT", "60")


@dataclass
class AIConfig:
    """Cấu hình AI provider cho discovery."""
    base_url: str = field(default_factory=lambda: _get_env("AI_PROVIDER_BASE_URL", ""))
    api_key: str = field(default_factory=lambda: _get_env("AI_API_KEY", ""))
    model: str = field(default_factory=lambda: _get_env("AI_MODEL", "openai/gpt-4o-mini"))
    timeout: int = field(default_factory=lambda: int(_get_env("AI_TIMEOUT", "60")))

    def is_configured(self) -> bool:
        """Kiểm tra đã có đủ config chưa."""
        return bool(self.base_url and self.api_key and self.model)

    def validate(self) -> list[str]:
        """Validate config, trả về list lỗi (rỗng = OK)."""
        errors = []
        if not self.base_url:
            errors.append("AI_PROVIDER_BASE_URL chưa được set")
        if not self.api_key:
            errors.append("AI_API_KEY chưa được set")
        if not self.model:
            errors.append("AI_MODEL chưa được set")
        if self.base_url and not self.base_url.startswith(("http://", "https://")):
            errors.append("AI_PROVIDER_BASE_URL phải bắt đầu bằng http:// hoặc https://")
        return errors


def _get_env(key: str, default: str) -> str:
    from dotenv import dotenv_values
    # Ưu tiên .env file, fallback os.environ
    vals = dotenv_values(_env_path) if _env_path.exists() else {}
    return vals.get(key, __import__("os").environ.get(key, default))


# Singleton config
ai_config = AIConfig()
