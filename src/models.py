"""
Data models cho Free LLM Provider Discovery
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ProviderStatus(str, Enum):
    """Trạng thái của provider"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"
    RATE_LIMITED = "rate_limited"


class AuthType(str, Enum):
    """Loại xác thực"""

    NONE = "none"
    API_KEY = "api_key"
    OAUTH = "oauth"


class APIStyle(str, Enum):
    """Chuẩn API"""

    OPENAI = "openai"  # /v1/chat/completions
    ANTHROPIC = "anthropic"  # /v1/messages
    CUSTOM = "custom"


class Model(BaseModel):
    """Model trong một provider"""

    id: str = Field(..., description="Model ID")
    name: str = Field(..., description="Tên model")
    is_free: bool = Field(True, description="Có miễn phí không")
    context_length: int | None = Field(None, description="Context length")
    description: str | None = Field(None, description="Mô tả model")
    supports_streaming: bool = Field(False, description="Có hỗ trợ streaming không")


class Provider(BaseModel):
    """Provider LLM"""

    name: str = Field(..., description="Tên provider")
    base_url: str = Field(..., description="Base URL của API")
    website: str | None = Field(None, description="Website của provider")
    description: str | None = Field(None, description="Mô tả provider")
    models: list[Model] = Field(default_factory=list, description="Danh sách model")
    status: ProviderStatus = Field(ProviderStatus.UNKNOWN, description="Trạng thái")
    auth_type: AuthType = Field(AuthType.API_KEY, description="Loại xác thực")
    api_style: APIStyle = Field(APIStyle.OPENAI, description="Chuẩn API")
    auth_required: bool = Field(True, description="Có yêu cầu xác thực không")
    rate_limit: str | None = Field(None, description="Rate limit")
    last_verified: datetime | None = Field(None, description="Lần kiểm tra cuối")
    tags: list[str] = Field(default_factory=list, description="Tags")

    def get_free_models(self) -> list[Model]:
        """Lấy danh sách model miễn phí"""
        return [m for m in self.models if m.is_free]


class ProviderList(BaseModel):
    """Danh sách provider"""

    providers: list[Provider] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = Field("1.0.0")
    total_count: int = Field(0)

    def model_post_init(self, __context):
        self.total_count = len(self.providers)
