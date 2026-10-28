"""
Keywords cho Deep Web Search — danh sách từ khoá dùng để quét internet.

Người dùng có thể truyền keyword tùy ý qua CLI (--keywords). Nếu không truyền,
dùng DEFAULT_KEYWORDS (preset đa ngôn ngữ: English + Vietnamese).
"""

from datetime import datetime, timezone

# Keyword preset — {year} sẽ được thay bằng năm hiện tại khi expand
DEFAULT_KEYWORDS: list[str] = [
    "free llm api provider",
    "free llm api {year}",
    "free tier llm api no credit card",
    "openai compatible free api",
    "llm free api key",
    "free ai api provider reddit",
    "nhà cung cấp LLM API miễn phí",
]

# Keyword scoping theo nền tảng — gắn site: khi query để tìm sâu hơn trên từng nguồn
PLATFORM_SCOPES: dict[str, str] = {
    "reddit": "site:reddit.com",
    "hackernews": "site:news.ycombinator.com",
    "duckduckgo": "",
    "github": "site:github.com",
}


def expand_keywords(keywords: list[str]) -> list[str]:
    """Thay placeholder {year} bằng năm hiện tại (UTC)."""
    year = str(datetime.now(timezone.utc).year)
    return [kw.replace("{year}", year) for kw in keywords]


def parse_keywords(raw: tuple[str, ...] | list[str] | None) -> list[str]:
    """
    Parse keyword từ CLI input (comma-separated) thành list sạch.

    - None / rỗng → dùng DEFAULT_KEYWORDS (đã expand {year})
    - Cho phép truyền nhiều --keyword hoặc 1 chuỗi "a, b, c"
    - Strip whitespace, bỏ item rỗng, dedupe giữ thứ tự
    """
    if not raw:
        return expand_keywords(DEFAULT_KEYWORDS)

    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        for part in item.split(","):
            kw = part.strip()
            if kw and kw.lower() not in seen:
                seen.add(kw.lower())
                result.append(kw)
    return expand_keywords(result)


def scope_keyword(keyword: str, source: str) -> str:
    """Thêm site-scoping cho keyword theo nguồn (vd: 'free llm api' + reddit → 'site:reddit.com ...')."""
    prefix = PLATFORM_SCOPES.get(source, "")
    if prefix and "site:" not in keyword.lower():
        return f"{prefix} {keyword}"
    return keyword
