"""
Data models cho Free LLM Provider Discovery
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


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
    context_length: Optional[int] = Field(None, description="Context length")
    description: Optional[str] = Field(None, description="Mô tả model")
    supports_streaming: bool = Field(False, description="Có hỗ trợ streaming không")


class Provider(BaseModel):
    """Provider LLM"""
    name: str = Field(..., description="Tên provider")
    base_url: str = Field(..., description="Base URL của API")
    website: Optional[str] = Field(None, description="Website của provider")
    description: Optional[str] = Field(None, description="Mô tả provider")
    models: List[Model] = Field(default_factory=list, description="Danh sách model")
    status: ProviderStatus = Field(ProviderStatus.UNKNOWN, description="Trạng thái")
    auth_type: AuthType = Field(AuthType.API_KEY, description="Loại xác thực")
    api_style: APIStyle = Field(APIStyle.OPENAI, description="Chuẩn API")
    auth_required: bool = Field(True, description="Có yêu cầu xác thực không")
    rate_limit: Optional[str] = Field(None, description="Rate limit")
    last_verified: Optional[datetime] = Field(None, description="Lần kiểm tra cuối")
    tags: List[str] = Field(default_factory=list, description="Tags")

    def get_free_models(self) -> List[Model]:
        """Lấy danh sách model miễn phí"""
        return [m for m in self.models if m.is_free]


class ProviderList(BaseModel):
    """Danh sách provider"""
    providers: List[Provider] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    version: str = Field("1.0.0")
    total_count: int = Field(0)

    def model_post_init(self, __context):
        self.total_count = len(self.providers)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
