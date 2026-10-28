"""
Deep Web Search Discovery — tìm provider LLM free trên nhiều nền tảng internet.

Khác với discover-live (chỉ OpenRouter) và discover-ai (trí nhớ LLM), module này
search THẬT trên Reddit / Hacker News / DuckDuckGo / GitHub với keyword linh hoạt,
rồi trích xuất Provider (heuristic regex hoặc AI đọc nội dung trang).
"""

from src.discovery.websearch.backends import (
    AVAILABLE_SOURCES,
    SEARCH_BACKENDS,
    SearchResult,
    parse_sources,
    run_search,
)
from src.discovery.websearch.deep_search import DeepSearchError, run_deep_search, search_only
from src.discovery.websearch.keywords import (
    DEFAULT_KEYWORDS,
    expand_keywords,
    parse_keywords,
    scope_keyword,
)

__all__ = [
    "AVAILABLE_SOURCES",
    "DEFAULT_KEYWORDS",
    "DeepSearchError",
    "SEARCH_BACKENDS",
    "SearchResult",
    "expand_keywords",
    "parse_keywords",
    "parse_sources",
    "run_deep_search",
    "run_search",
    "scope_keyword",
    "search_only",
]
