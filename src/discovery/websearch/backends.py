"""
Search backends cho Deep Web Search — query các nền tảng public KHÔNG cần API key.

Mỗi backend trả về list[SearchResult]. Lỗi network/schema KHÔNG BAO GIỜ crash —
backend ghi warning và trả về list rỗng (nguyên tắc graceful như webhook).
"""

import re
import time
from dataclasses import dataclass, field
from urllib.parse import quote_plus

import httpx
from rich.console import Console

from src.__version__ import __version__

console = Console()

DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_RESULTS = 10
RETRY_BACKOFF_BASE = 1.0
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# Reddit chặn User-Agent mặc định của httpx — phải tự định danh
HEADERS = {
    "User-Agent": f"free-llm-provider-discovery/{__version__} (discovery research tool)",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}


@dataclass
class SearchResult:
    """Một kết quả tìm kiếm từ bất kỳ backend nào."""

    title: str
    url: str
    snippet: str = ""
    source: str = ""  # reddit | hackernews | duckduckgo | github
    extra: dict = field(default_factory=dict)


def _http_get(url: str, timeout: float = DEFAULT_TIMEOUT) -> httpx.Response:
    """GET với retry exponential backoff cho lỗi tạm thời (429/5xx/timeout)."""
    last_error: str | None = None
    for attempt in range(2):
        try:
            resp = httpx.get(url, timeout=timeout, headers=HEADERS, follow_redirects=True)
            resp.raise_for_status()
            return resp
        except httpx.TimeoutException:
            last_error = f"Timeout sau {timeout}s khi gọi {url}"
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in RETRYABLE_STATUS_CODES and attempt < 1:
                last_error = f"HTTP {status} từ {url}"
                console.print(f"[yellow]⚠ {last_error}. Thử lại...[/yellow]")
                time.sleep(RETRY_BACKOFF_BASE * (2**attempt))
                continue
            raise
    raise httpx.HTTPError(last_error or f"Lỗi không xác định khi gọi {url}")


def _safe_backend(name: str, fn, query: str, max_results: int, timeout: float) -> list[SearchResult]:
    """Chạy 1 backend, nuốt mọi exception → trả về [] với warning (graceful)."""
    try:
        return fn(query, max_results, timeout)
    except Exception as e:  # noqa: BLE001 — graceful degradation là chủ đích
        console.print(f"[yellow]⚠ Source '{name}' lỗi, bỏ qua: {e}[/yellow]")
        return []


# ---------------------------------------------------------------------------
# Reddit — JSON API public: reddit.com/search.json
# ---------------------------------------------------------------------------

def search_reddit(query: str, max_results: int = DEFAULT_MAX_RESULTS, timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """Search posts Reddit (public JSON, không cần key)."""
    url = (
        "https://www.reddit.com/search.json"
        f"?q={quote_plus(query)}&limit={max_results}&sort=relevance&t=year"
    )
    resp = _http_get(url, timeout)
    data = resp.json()
    results: list[SearchResult] = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        title = post.get("title") or ""
        permalink = post.get("permalink") or ""
        if not title or not permalink:
            continue
        results.append(
            SearchResult(
                title=title,
                url=f"https://www.reddit.com{permalink}",
                snippet=str(post.get("selftext") or "")[:500],
                source="reddit",
                extra={"subreddit": post.get("subreddit", "")},
            )
        )
    return results[:max_results]


# ---------------------------------------------------------------------------
# Hacker News — Algolia API public: hn.algolia.com/api/v1/search
# ---------------------------------------------------------------------------

def search_hackernews(query: str, max_results: int = DEFAULT_MAX_RESULTS, timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """Search stories trên Hacker News (Algolia API public, không cần key)."""
    url = f"https://hn.algolia.com/api/v1/search?query={quote_plus(query)}&tags=story&hitsPerPage={max_results}"
    resp = _http_get(url, timeout)
    data = resp.json()
    results: list[SearchResult] = []
    for hit in data.get("hits", []):
        title = hit.get("title") or ""
        story_url = hit.get("url") or ""
        if not title:
            continue
        # Story không có link ngoài vẫn giữ (dùng URL discuss trên HN)
        if not story_url:
            object_id = hit.get("objectID") or ""
            if not object_id:
                continue
            story_url = f"https://news.ycombinator.com/item?id={object_id}"
        results.append(
            SearchResult(
                title=title,
                url=story_url,
                snippet=str(hit.get("story_text") or hit.get("comment_text") or "")[:500],
                source="hackernews",
                extra={"points": hit.get("points", 0)},
            )
        )
    return results[:max_results]


# ---------------------------------------------------------------------------
# DuckDuckGo — HTML lite endpoint, parse bằng regex (không cần thư viện ngoài)
# ---------------------------------------------------------------------------

_DDG_LINK_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*class="result__a"[^>]*>(.*?)</a>', re.DOTALL)
_DDG_LINK_RE_ALT = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DDG_REDIRECT_RE = re.compile(r"[?&]uddg=([^&]+)")


def _clean_html(raw: str) -> str:
    return _HTML_TAG_RE.sub("", raw).strip()


def _resolve_ddg_url(url: str) -> str:
    """DDG đôi khi trả redirect link //duckduckgo.com/l/?uddg=<encoded> — giải mã ra URL thật."""
    match = _DDG_REDIRECT_RE.search(url)
    if match:
        from urllib.parse import unquote

        return unquote(match.group(1))
    return url


# DuckDuckGo html endpoint chặn bot bằng HTTP 202 challenge với UA lạ —
# dùng POST form + browser UA để nhận kết quả thật (HTTP 200)
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://duckduckgo.com/",
    "Accept": "text/html,application/xhtml+xml",
}


def search_duckduckgo(query: str, max_results: int = DEFAULT_MAX_RESULTS, timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """Search DuckDuckGo (HTML endpoint, không cần key — unofficial, có thể flaky)."""
    resp = httpx.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers=BROWSER_HEADERS,
        timeout=timeout,
        follow_redirects=True,
    )
    resp.raise_for_status()
    html = resp.text

    results: list[SearchResult] = []
    matches = _DDG_LINK_RE.findall(html) or _DDG_LINK_RE_ALT.findall(html)
    for link, title_html in matches:
        real_url = _resolve_ddg_url(link)
        title = _clean_html(title_html)
        if not title or not real_url:
            continue
        results.append(SearchResult(title=title, url=real_url, source="duckduckgo"))
    return results[:max_results]


# ---------------------------------------------------------------------------
# GitHub — Search API public (unauthenticated, 10 req/phút)
# ---------------------------------------------------------------------------

def search_github(query: str, max_results: int = DEFAULT_MAX_RESULTS, timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """Search repos GitHub về free LLM API (awesome-lists, tools, ...)."""
    url = (
        f"https://api.github.com/search/repositories?q={quote_plus(query)}"
        f"&per_page={max_results}&sort=stars&order=desc"
    )
    resp = _http_get(url, timeout)
    data = resp.json()
    results: list[SearchResult] = []
    for item in data.get("items", []):
        full_name = item.get("full_name") or ""
        if not full_name:
            continue
        results.append(
            SearchResult(
                title=full_name,
                url=item.get("html_url") or f"https://github.com/{full_name}",
                snippet=str(item.get("description") or "")[:500],
                source="github",
                extra={"stars": item.get("stargazers_count", 0)},
            )
        )
    return results[:max_results]


# ---------------------------------------------------------------------------
# Registry + orchestration
# ---------------------------------------------------------------------------

SEARCH_BACKENDS = {
    "reddit": search_reddit,
    "hackernews": search_hackernews,
    "duckduckgo": search_duckduckgo,
    "github": search_github,
}

AVAILABLE_SOURCES = sorted(SEARCH_BACKENDS.keys())


def parse_sources(raw: str | None) -> list[str]:
    """Parse --sources 'reddit,hn' → list tên backend hợp lệ. None/rỗng = tất cả."""
    if not raw or not raw.strip():
        return AVAILABLE_SOURCES
    valid: list[str] = []
    for part in raw.split(","):
        name = part.strip().lower()
        # alias thân thiện
        aliases = {"hn": "hackernews", "ddg": "duckduckgo", "gh": "github"}
        name = aliases.get(name, name)
        if name in SEARCH_BACKENDS and name not in valid:
            valid.append(name)
        elif name not in SEARCH_BACKENDS:
            console.print(f"[yellow]⚠ Nguồn không hợp lệ: '{part.strip()}' (bỏ qua). "
                          f"Các nguồn hợp lệ: {', '.join(AVAILABLE_SOURCES)}[/yellow]")
    return valid or AVAILABLE_SOURCES


def run_search(
    keywords: list[str],
    sources: list[str] | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[SearchResult]:
    """
    Chạy search trên nhiều nguồn × nhiều keyword.

    - Dedupe kết quả theo URL (giữ kết quả đầu tiên)
    - Lỗi 1 nguồn không ảnh hưởng nguồn khác
    """
    if sources is None:
        sources = AVAILABLE_SOURCES

    seen_urls: set[str] = set()
    results: list[SearchResult] = []
    for source in sources:
        backend = SEARCH_BACKENDS.get(source)
        if backend is None:
            continue
        found = 0
        for keyword in keywords:
            scoped = keyword if "site:" in keyword.lower() else keyword
            for r in _safe_backend(source, backend, scoped, max_results, timeout):
                if r.url.lower() in seen_urls:
                    continue
                seen_urls.add(r.url.lower())
                results.append(r)
                found += 1
        console.print(f"[dim]  • {source}: {found} kết quả[/dim]")
    return results
