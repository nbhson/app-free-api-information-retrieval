"""
Extractor cho Deep Web Search — biến kết quả search thành candidate Provider.

2 chế độ bổ trợ nhau:
- Heuristic (không cần AI key): regex tìm URL API thật (/v1, /api) trong
  title/snippet/URL — rẻ, nhanh, chỉ bắt được provider lộ endpoint công khai.
- AI (cần .env): fetch nội dung trang thật, gửi cho LLM trích xuất Provider
  theo schema — sâu hơn, bắt được cả provider chỉ được đề cập trong bài viết.
"""

import re
from urllib.parse import urlparse

import httpx
from rich.console import Console

from src.config import AIConfig
from src.discovery.ai_agent import _extract_json
from src.models import Provider

console = Console()

# Domain không bao giờ là LLM provider — lọc nhiễu từ kết quả social/search
BLOCKED_DOMAINS = frozenset(
    {
        "reddit.com",
        "news.ycombinator.com",
        "duckduckgo.com",
        "google.com",
        "youtube.com",
        "facebook.com",
        "twitter.com",
        "x.com",
        "instagram.com",
        "linkedin.com",
        "wikipedia.org",
        "medium.com",
        "github.com",
        "stackoverflow.com",
        "quora.com",
        "algolia.com",
        "hn.algolia.com",
    }
)

# URL giống endpoint API: .../v1 hoặc /api/... trên 1 domain bất kỳ
_API_URL_RE = re.compile(
    r"https?://(?P<host>[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?)"
    r"(?::\d{2,5})?"
    r"(?P<path>/v1(?:/[a-zA-Z0-9._-]*)?|/api(?:/[a-zA-Z0-9._/-]*)?)"
)

MAX_PAGE_CHARS = 6000  # truncate nội dung trang trước khi gửi cho LLM


# ---------------------------------------------------------------------------
# Heuristic extraction
# ---------------------------------------------------------------------------


def _domain_of(url: str) -> str:
    """Lấy domain gốc (bỏ www.) từ URL — trả '' nếu parse lỗi."""
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.")


def _is_blocked(url: str) -> bool:
    """Domain của URL có nằm trong blocklist (social/search noise) không."""
    domain = _domain_of(url)
    return any(domain == d or domain.endswith("." + d) for d in BLOCKED_DOMAINS)


def _provider_name_from_host(host: str) -> str:
    """'api.groq.com' → 'Groq'; 'openrouter.ai' → 'Openrouter'."""
    parts = host.removeprefix("api.").split(".")
    core = parts[0] if parts else host
    return core.replace("-", " ").title()


def extract_heuristic(results: list) -> list[Provider]:
    """
    Regex tìm URL API thật trong title/snippet/URL của search results.

    - Nhóm theo domain, 1 domain = 1 candidate Provider
    - Chỉ tạo Provider khi tìm thấy endpoint rõ ràng (không bịa base_url)
    - Đã dedupe theo base_url
    """
    candidates: dict[str, tuple[str, str]] = {}  # domain -> (api_url, title)
    for r in results:
        texts = [r.title, r.snippet, r.url]
        for text in texts:
            for match in _API_URL_RE.finditer(text):
                host = match.group("host").lower().removeprefix("www.")
                if not host or any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS):
                    continue
                api_url = f"https://{host}{match.group('path').rstrip('/')}"
                if host not in candidates:
                    candidates[host] = (api_url, r.title)

    providers: list[Provider] = []
    for host, (api_url, title) in candidates.items():
        providers.append(
            Provider(
                name=_provider_name_from_host(host),
                base_url=api_url,
                website=f"https://{host}",
                description=f"Heuristic web-discovered từ kết quả search: '{title[:100]}'",
                models=[],
                tags=["web-discovered", "heuristic", "unverified"],
            )
        )
    return providers


# ---------------------------------------------------------------------------
# Page fetching (cho AI extraction)
# ---------------------------------------------------------------------------


def fetch_page_text(url: str, timeout: float = 15.0, max_chars: int = MAX_PAGE_CHARS) -> str:
    """
    GET trang, trả về text (đã truncate). Trả '' khi mọi lỗi — caller tự quyết.
    Chỉ chấp nhận content-type text/* và json để tránh tải binary.
    """
    try:
        resp = httpx.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "free-llm-provider-discovery"},
            follow_redirects=True,
        )
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "text/" not in content_type and "json" not in content_type:
            return ""
        return resp.text[:max_chars]
    except Exception as e:  # noqa: BLE001 — 1 trang lỗi không được chặn pipeline
        console.print(f"[yellow]⚠ Không fetch được {url}: {e}[/yellow]")
        return ""


def collect_page_contexts(
    results: list, max_pages: int = 5, timeout: float = 15.0
) -> list[tuple[str, str]]:
    """Fetch text của tối đa `max_pages` URL (bỏ social domain). Trả [(url, text)]."""
    contexts: list[tuple[str, str]] = []
    for r in results:
        if len(contexts) >= max_pages:
            break
        if _is_blocked(r.url):
            continue
        text = fetch_page_text(r.url, timeout)
        if text:
            contexts.append((r.url, text))
    return contexts


# ---------------------------------------------------------------------------
# AI extraction — LLM đọc nội dung web THẬT (khác discover-ai chỉ hỏi trí nhớ)
# ---------------------------------------------------------------------------

AI_EXTRACT_SYSTEM_PROMPT = """Bạn là chuyên gia nghiên cứu LLM API providers.
Dưới đây là nội dung TRẢ VỀ THẬT TỪ INTERNET (search results + trang web).
Nhiệm vụ: trích xuất các nhà cung cấp API LLM MIỄN PHÍ (free tier) được đề cập.

Chỉ trả về JSON thuần (không markdown, không giải thích), schema:

{
  "providers": [
    {
      "name": "Tên provider",
      "base_url": "https://... endpoint API chính thức",
      "website": "https://... trang chủ",
      "description": "Mô tả ngắn",
      "api_style": "openai | anthropic | custom",
      "auth_required": true/false,
      "rate_limit": "giới hạn free tier",
      "tags": ["tag1", "tag2"],
      "free_models": [{"id": "model-id", "name": "Tên", "context_length": 8192}]
    }
  ]
}

Lưu ý:
- CHỈ trích xuất provider được đề cập THẬT trong nội dung — tuyệt đối không bịa
  từ trí nhớ của bạn. Không thấy provider nào → trả về {"providers": []}.
- base_url phải có trong nội dung hoặc suy ra trực tiếp từ domain được đề cập."""


def extract_with_ai(
    contexts: list[tuple[str, str]],
    results: list,
    keywords: list[str],
    config: AIConfig,
) -> list[Provider]:
    """
    Gửi nội dung web thật cho LLM để trích xuất Provider.

    Raises:
        RuntimeError: khi LLM API lỗi hoặc response sai cấu trúc.
    """
    if not contexts and not results:
        return []

    url = f"{config.base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}

    # Ghép search snippets (rẻ) + nội dung trang (sâu) thành context duy nhất
    parts = ["## Kết quả tìm kiếm (title + snippet):"]
    for r in results[:15]:
        snippet = r.snippet[:300]
        parts.append(f"- [{r.source}] {r.title} — {r.url}\n  {snippet}")
    if contexts:
        parts.append("\n## Nội dung các trang web (đã truncate):")
        for page_url, text in contexts:
            parts.append(f"### Trang: {page_url}\n{text}")

    user_content = f"Người dùng đang tìm kiếm với từ khoá: {', '.join(keywords)}\n\n" + "\n".join(
        parts
    )

    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": AI_EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": user_content[:30000]},
        ],
        "temperature": 0.1,
    }

    resp = httpx.post(url, headers=headers, json=payload, timeout=config.timeout)
    if resp.status_code in (401, 403):
        raise RuntimeError(f"AI API key sai hoặc hết hạn (HTTP {resp.status_code})")
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    parsed = _extract_json(content)

    from src.discovery.ai_agent import _parse_providers

    providers = _parse_providers(parsed)
    # Đổi tag: đây là web-discovered (AI chỉ là công cụ trích xuất), không phải ai-discovered
    for p in providers:
        p.tags = [t for t in p.tags if t != "ai-discovered"]
        if "web-discovered" not in p.tags:
            p.tags.append("web-discovered")
        if "deep-search" not in p.tags:
            p.tags.append("deep-search")
    return providers
