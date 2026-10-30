"""
Search backends cho Deep Web Search — query các nền tảng public KHÔNG cần API key.

Mỗi backend trả về list[SearchResult]. Lỗi network/schema KHÔNG BAO GIỜ crash —
backend ghi warning và trả về list rỗng (nguyên tắc graceful như webhook).
"""

import re
import time
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urlparse

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
    source: str = ""  # reddit | hackernews | duckduckgo | google | github | shared_keys
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


def _safe_backend(
    name: str, fn, query: str, max_results: int, timeout: float
) -> list[SearchResult]:
    """Chạy 1 backend, nuốt mọi exception → trả về [] với warning (graceful)."""
    try:
        return fn(query, max_results, timeout)
    except Exception as e:  # noqa: BLE001 — graceful degradation là chủ đích
        console.print(f"[yellow]⚠ Source '{name}' lỗi, bỏ qua: {e}[/yellow]")
        return []


# ---------------------------------------------------------------------------
# Reddit — JSON API public: reddit.com/search.json
# ---------------------------------------------------------------------------


def search_reddit(
    query: str, max_results: int = DEFAULT_MAX_RESULTS, timeout: float = DEFAULT_TIMEOUT
) -> list[SearchResult]:
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


def search_hackernews(
    query: str, max_results: int = DEFAULT_MAX_RESULTS, timeout: float = DEFAULT_TIMEOUT
) -> list[SearchResult]:
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
_DDG_LINK_RE_ALT = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL
)
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


def search_duckduckgo(
    query: str, max_results: int = DEFAULT_MAX_RESULTS, timeout: float = DEFAULT_TIMEOUT
) -> list[SearchResult]:
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


def search_github(
    query: str, max_results: int = DEFAULT_MAX_RESULTS, timeout: float = DEFAULT_TIMEOUT
) -> list[SearchResult]:
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
# Shared-key community pools — crown.ai.id (status API public) + LMSpeed
# (bảng shared keys do cộng đồng submit). Đây là nguồn "bansos": API key
# miễn phí do cộng đồng chia sẻ, OpenAI-compatible.
# ---------------------------------------------------------------------------


def _domain_of_url(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return url
    return host.lower().removeprefix("www.")


CROWN_STATUS_URL = "https://crown.ai.id/api/status"
CROWN_BANSOS_URL = "https://crown.ai.id/bansos"

LMSPEED_SHARED_KEYS_URL = "https://lmspeed.net/free-api-keys"
# Provider link có thể là relative (/provider/x) hoặc absolute (https://lmspeed.net/provider/x)
_LMSPEED_PROVIDER_RE = re.compile(r'href="(?:https://lmspeed\.net)?(/provider/[a-zA-Z0-9._-]+)"')
# RSC payload nhúng baseUrl thật của shared key: baseUrl:"https://api.xxx/v1"
_LMSPEED_BASE_URL_RE = re.compile(r'baseUrl:"(https://[^"]+)"')

# Trang cộng đồng Indonesia chia sẻ key free (vd: ai.masb.web.id) —
# scrape generic: tìm mọi URL API OpenAI-compatible (/v1) trong HTML
_MASB_URL = "https://ai.masb.web.id/"
# Endpoint API xuất hiện trong HTML: href hoặc text thuần
_API_URL_ANY_RE = re.compile(
    r"https?://(?P<host>[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?)"
    r"(?::\d{2,5})?"
    r"/v1(?:/[a-zA-Z0-9._/-]*)?"
)


def fetch_masb_shared_keys(timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """
    Scrape ai.masb.web.id — trang cộng đồng Indonesia chia sẻ key/API LLM free.
    Trích xuất mọi endpoint /v1 xuất hiện trong HTML (href, text, JS payload).
    """
    resp = httpx.get(_MASB_URL, timeout=timeout, headers=BROWSER_HEADERS, follow_redirects=True)
    resp.raise_for_status()
    html = resp.text

    results: list[SearchResult] = []
    seen: set[str] = set()
    for match in _API_URL_ANY_RE.finditer(html):
        api_url = match.group(0).rstrip("/")
        host = _domain_of_url(api_url)
        if not host or api_url.lower() in seen:
            continue
        # Bỏ chính domain masb (không phải provider)
        if host == "ai.masb.web.id" or host.endswith(".masb.web.id"):
            continue
        seen.add(api_url.lower())
        results.append(
            SearchResult(
                title=f"{host} (shared key trên masb.web.id)",
                url=api_url,
                snippet=f"Community-shared free API endpoint từ ai.masb.web.id — base URL {api_url}",
                source="shared_keys",
            )
        )
    return results


def fetch_crown_bansos(timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """
    Fetch trang crown.ai.id/bansos — trang bansos (bantuan sosial = trợ cấp)
    của Crown AI: nơi phát key free cho cộng đồng. Trích xuất endpoint API
    và hướng dẫn lấy key để đưa vào context cho AI extraction.
    """
    resp = httpx.get(CROWN_BANSOS_URL, timeout=timeout, headers=BROWSER_HEADERS, follow_redirects=True)
    resp.raise_for_status()
    html = resp.text

    results: list[SearchResult] = []
    seen: set[str] = set()
    for match in _API_URL_ANY_RE.finditer(html):
        api_url = match.group(0).rstrip("/")
        host = _domain_of_url(api_url)
        if not host or api_url.lower() in seen:
            continue
        seen.add(api_url.lower())
        results.append(
            SearchResult(
                title=f"{host} (free key từ crown.ai.id/bansos)",
                url=api_url,
                snippet=f"Free community API key phát tại https://crown.ai.id/bansos — base URL {api_url}",
                source="shared_keys",
            )
        )
    return results


def fetch_lmspeed_shared_keys(timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """
    Scrape bảng shared keys của LMSpeed — key do cộng đồng submit (bị mask
    nhưng provider + base_url hiển thị công khai trong RSC payload).
    """
    resp = httpx.get(
        LMSPEED_SHARED_KEYS_URL,
        timeout=timeout,
        headers=BROWSER_HEADERS,
        follow_redirects=True,
    )
    resp.raise_for_status()
    html = resp.text

    results: list[SearchResult] = []
    seen: set[str] = set()

    # 1) baseUrl thật từ RSC payload — đây là endpoint API cộng đồng đang chia sẻ
    for base_url in dict.fromkeys(re.findall(r'baseUrl:"(https://[^"]+)"', html)):
        if base_url.lower() in seen:
            continue
        seen.add(base_url)
        host = _domain_of_url(base_url)
        results.append(
            SearchResult(
                title=f"{host} (shared key trên LMSpeed)",
                url=base_url,
                snippet=f"Community-submitted shared API key — base URL {base_url} "
                "(OpenAI-compatible, chi tiết tại LMSpeed)",
                source="shared_keys",
            )
        )

    # 2) Provider pages — context bổ sung cho AI extraction
    for path in _LMSPEED_PROVIDER_RE.findall(html):
        provider_url = f"https://lmspeed.net{path}"
        if provider_url in seen:
            continue
        seen.add(provider_url)
        name = path.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()
        results.append(
            SearchResult(
                title=f"{name} (shared key trên LMSpeed)",
                url=provider_url,
                snippet="Community-submitted shared API key — xem chi tiết tại LMSpeed",
                source="shared_keys",
            )
        )
    return results


def search_shared_keys(
    query: str, max_results: int = DEFAULT_MAX_RESULTS, timeout: float = DEFAULT_TIMEOUT
) -> list[SearchResult]:
    """
    Nguồn 'shared' — trang web chia sẻ API key cộng đồng (không cần key):
    - Crown AI status API: pool sống/chết, model nào online ngay bây giờ
    - LMSpeed shared keys: provider nào đang được cộng đồng chia sẻ key
    Kết quả trả về dạng SearchResult để đi qua pipeline extract/dedupe chuẩn.
    """
    results: list[SearchResult] = []

    # Crown AI — JSON public, luôn trả model alive hiện tại
    try:
        resp = _http_get(CROWN_STATUS_URL, timeout)
        data = resp.json().get("data", {})
        pool = data.get("pool", {})
        alive = [m.get("id") for m in data.get("models", []) if m.get("alive")]
        if alive:
            results.append(
                SearchResult(
                    title="Crown AI community pool (bansos) — free shared API key",
                    url="https://crown.ai.id",
                    snippet=(
                        f"Base URL: https://crown.ai.id/v1 (OpenAI-compatible). "
                        f"Free community API key: https://crown.ai.id/bansos. "
                        f"Models online: {', '.join(str(m) for m in alive)}. "
                        f"Pool: {pool.get('alive_keys', '?')}/{pool.get('keys_checked', '?')} keys alive."
                    ),
                    source="shared_keys",
                    extra={"models_online": alive, "pool": pool},
                )
            )
    except Exception as e:  # noqa: BLE001 — graceful như mọi backend khác
        console.print(f"[yellow]⚠ Crown AI status API lỗi, bỏ qua: {e}[/yellow]")

    # LMSpeed — bảng shared keys (provider name công khai, key bị mask)
    try:
        results.extend(fetch_lmspeed_shared_keys(timeout))
    except Exception as e:  # noqa: BLE001
        console.print(f"[yellow]⚠ LMSpeed shared keys lỗi, bỏ qua: {e}[/yellow]")

    # Crown bansos — trang phát key free của cộng đồng Indonesia
    try:
        results.extend(fetch_crown_bansos(timeout))
    except Exception as e:  # noqa: BLE001
        console.print(f"[yellow]⚠ Crown bansos lỗi, bỏ qua: {e}[/yellow]")

    # masb.web.id — trang cộng đồng Indonesia chia sẻ key/API free
    try:
        results.extend(fetch_masb_shared_keys(timeout))
    except Exception as e:  # noqa: BLE001
        console.print(f"[yellow]⚠ masb.web.id lỗi, bỏ qua: {e}[/yellow]")

    # Nguồn shared trả kết quả trực tiếp (không qua search) — không cắt
    # theo max_results của search (tránh mất provider khi thêm nguồn mới)
    return results[: max(max_results, 50)]


# ---------------------------------------------------------------------------
# Social (X/Twitter, Threads, Instagram) — site-scoped search qua Google/DuckDuckGo
# ---------------------------------------------------------------------------

# Nền tảng social + site: scope cho Google/DDG. Lưu ý: X/Instagram/Threads
# KHÔNG có search API public miễn phí — cách đáng tin nhất là search qua
# Google index với site: scope (CSE khi có key, DDG html khi không có).
SOCIAL_SCOPES = {
    "x": "site:x.com OR site:twitter.com",
    "threads": "site:threads.net",
    "instagram": "site:instagram.com",
}


def search_social(
    query: str, max_results: int = DEFAULT_MAX_RESULTS, timeout: float = DEFAULT_TIMEOUT
) -> list[SearchResult]:
    """
    Nguồn 'social' — tìm bài đăng về free LLM API trên X/Twitter, Threads,
    Instagram thông qua Google index (site: scope) + DuckDuckGo fallback.

    - Có GOOGLE_API_KEY + GOOGLE_CSE_ID → Google Custom Search (đáng tin nhất)
    - Không → DuckDuckGo html (hỗ trợ site: operator, không cần key)
    - 1 nền tảng lỗi → bỏ qua, các nền tảng khác vẫn chạy (graceful)
    """
    from src.config import get_google_config

    gcfg = get_google_config()
    use_cse = gcfg.is_configured()
    results: list[SearchResult] = []
    seen: set[str] = set()

    for platform, scope in SOCIAL_SCOPES.items():
        scoped_query = f"{query} {scope}"
        platform_results: list[SearchResult] = []
        if use_cse:
            platform_results = _safe_backend(
                f"google-cse/{platform}", _google_cse_search, scoped_query, max_results, timeout
            )
        if not platform_results:
            platform_results = _safe_backend(
                f"duckduckgo/{platform}",
                _ddg_search_raw,
                scoped_query,
                max_results,
                timeout,
            )
        for r in platform_results:
            if r.url.lower() in seen:
                continue
            seen.add(r.url.lower())
            r.source = "social"
            r.extra.setdefault("platform", platform)
            results.append(r)
    return results[:max_results]


def _google_cse_search(
    query: str, max_results: int, timeout: float
) -> list[SearchResult]:
    """Google Custom Search JSON API — trả list[SearchResult] (raise khi lỗi)."""
    from src.config import get_google_config

    gcfg = get_google_config()
    url = (
        f"{GOOGLE_CSE_URL}"
        f"?key={gcfg.api_key}&cx={gcfg.cse_id}&q={quote_plus(query)}&num={min(max_results, 10)}"
    )
    resp = _http_get(url, timeout)
    data = resp.json()
    results: list[SearchResult] = []
    for item in data.get("items", []):
        title = item.get("title") or ""
        link = item.get("link") or ""
        if not title or not link:
            continue
        results.append(
            SearchResult(
                title=title,
                url=link,
                snippet=str(item.get("snippet") or "")[:500],
                source="social",
                extra={"display_link": item.get("displayLink", "")},
            )
        )
    return results[:max_results]


def _ddg_search_raw(
    query: str, max_results: int, timeout: float
) -> list[SearchResult]:
    """DuckDuckGo html search raw — dùng cho site: scoped queries (social)."""
    return search_duckduckgo(query, max_results, timeout)


# ---------------------------------------------------------------------------
# Google — Custom Search JSON API (nếu có key) hoặc Google News RSS (public)
# ---------------------------------------------------------------------------

GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1/search"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"


def _parse_google_news_rss(xml_text: str, max_results: int) -> list[SearchResult]:
    """Parse Google News RSS XML → list[SearchResult] (không thêm dependency)."""
    import xml.etree.ElementTree as ET

    results: list[SearchResult] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise RuntimeError(f"Google News RSS XML lỗi: {e}") from e
    # RSS: <rss><channel><item>...
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        pub_date = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source_name = (source_el.text or "").strip() if source_el is not None else ""
        snippet = (item.findtext("description") or "").strip()
        # Bỏ HTML tag trong description (Google News nhúng <a>,...)
        snippet = _HTML_TAG_RE.sub("", snippet)[:500]
        results.append(
            SearchResult(
                title=_clean_html(title),
                url=link,
                snippet=f"{snippet} ({source_name}) {pub_date}".strip()[:500],
                source="google",
                extra={"news_source": source_name},
            )
        )
        if len(results) >= max_results:
            break
    return results


def search_google(
    query: str, max_results: int = DEFAULT_MAX_RESULTS, timeout: float = DEFAULT_TIMEOUT
) -> list[SearchResult]:
    """
    Search Google cho deep web search — 2 tầng theo độ tin cậy:

    1. **Google Custom Search JSON API** (khi .env có GOOGLE_API_KEY +
       GOOGLE_CSE_ID): web index THẬT của Google, kết quả đáng tin nhất,
       có snippet — đây là tầng ưu tiên ("bất cứ giá nào").
    2. **Google News RSS** (fallback, không cần key): index tin tức của
       Google, public, ổn định — dùng khi chưa cấu hình Custom Search.

    Lỗi 1 tầng → tự chuyển tầng dưới, không crash (graceful).
    """
    from src.config import get_google_config

    gcfg = get_google_config()
    if gcfg.is_configured():
        try:
            url = (
                f"{GOOGLE_CSE_URL}"
                f"?key={gcfg.api_key}&cx={gcfg.cse_id}"
                f"&q={quote_plus(query)}&num={min(max_results, 10)}"
            )
            resp = _http_get(url, timeout)
            data = resp.json()
            results: list[SearchResult] = []
            for item in data.get("items", []):
                title = item.get("title") or ""
                link = item.get("link") or ""
                if not title or not link:
                    continue
                results.append(
                    SearchResult(
                        title=title,
                        url=link,
                        snippet=str(item.get("snippet") or "")[:500],
                        source="google",
                        extra={"display_link": item.get("displayLink", "")},
                    )
                )
            if results:
                return results[:max_results]
            console.print("[yellow]⚠ Google CSE trả về rỗng → fallback Google News RSS[/yellow]")
        except Exception as e:  # noqa: BLE001 — fallback RSS thay vì crash
            console.print(f"[yellow]⚠ Google Custom Search lỗi ({e}) → fallback News RSS[/yellow]")

    # Fallback: Google News RSS (public, không cần key)
    url = f"{GOOGLE_NEWS_RSS_URL}?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    resp = _http_get(url, timeout)
    return _parse_google_news_rss(resp.text, max_results)


# ---------------------------------------------------------------------------
# Registry + orchestration
# ---------------------------------------------------------------------------

SEARCH_BACKENDS = {
    "reddit": search_reddit,
    "hackernews": search_hackernews,
    "duckduckgo": search_duckduckgo,
    "google": search_google,
    "social": search_social,
    "github": search_github,
    "shared": search_shared_keys,
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
        aliases = {"hn": "hackernews", "ddg": "duckduckgo", "gh": "github", "g": "google"}
        name = aliases.get(name, name)
        if name in SEARCH_BACKENDS and name not in valid:
            valid.append(name)
        elif name not in SEARCH_BACKENDS:
            console.print(
                f"[yellow]⚠ Nguồn không hợp lệ: '{part.strip()}' (bỏ qua). "
                f"Các nguồn hợp lệ: {', '.join(AVAILABLE_SOURCES)}[/yellow]"
            )
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
            for r in _safe_backend(source, backend, keyword, max_results, timeout):
                if r.url.lower() in seen_urls:
                    continue
                seen_urls.add(r.url.lower())
                results.append(r)
                found += 1
        console.print(f"[dim]  • {source}: {found} kết quả[/dim]")
    return results
