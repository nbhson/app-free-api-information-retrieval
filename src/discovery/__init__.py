"""
Discovery Module - Registry tất cả provider LLM miễn phí
"""

from .providers_part1 import KNOWN_PROVIDERS_PART1 as PART1
from .providers_part2 import KNOWN_PROVIDERS_PART2 as PART2

# Tổng hợp tất cả provider
KNOWN_PROVIDERS = PART1 + PART2

# Registry tra cứu nhanh theo tên
PROVIDER_REGISTRY = {p.name.lower(): p for p in KNOWN_PROVIDERS}


def get_provider_by_name(name: str):
    """Tìm provider theo tên (không phân biệt hoa thường)"""
    return PROVIDER_REGISTRY.get(name.lower())


def get_providers_by_tag(tag: str):
    """Lọc provider theo tag (ví dụ: 'free-tier', 'openai-compatible')"""
    return [p for p in KNOWN_PROVIDERS if tag in p.tags]


def get_providers_no_auth():
    """Provider không cần API key"""
    return [p for p in KNOWN_PROVIDERS if not p.auth_required]


__all__ = [
    "KNOWN_PROVIDERS",
    "PROVIDER_REGISTRY",
    "get_provider_by_name",
    "get_providers_by_tag",
    "get_providers_no_auth",
]
