"""Tests cho src.discovery.websearch (mock HTTP, không gọi mạng thật)."""

import json

import httpx
import pytest

from src.discovery.websearch.backends import (
    AVAILABLE_SOURCES,
    SearchResult,
    _resolve_ddg_url,
    parse_sources,
    run_search,
    search_duckduckgo,
    search_github,
    search_hackernews,
    search_reddit,
)
from src.discovery.websearch.deep_search import dedupe_providers, run_deep_search
from src.discovery.websearch.extractor import (
    _domain_of,
    _is_blocked,
    _provider_name_from_host,
    extract_heuristic,
    fetch_page_text,
)
from src.discovery.websearch.keywords import (
    DEFAULT_KEYWORDS,
    expand_keywords,
    parse_keywords,
    scope_keyword,
)
from src.models import Provider


@pytest.fixture
def runner() -> "object":
    from click.testing import CliRunner

    return CliRunner()


def _result(
    url: str, title: str = "Title", snippet: str = "", source: str = "reddit"
) -> SearchResult:
    return SearchResult(title=title, url=url, snippet=snippet, source=source)


def _fake_json_resp(payload):
    class FakeResponse:
        status_code = 200
        text = ""
        headers = {"content-type": "application/json"}

        def json(self):
            return payload

        def raise_for_status(self):
            pass

    return FakeResponse()


def _fake_html_resp(html):
    class FakeResponse:
        status_code = 200
        text = html
        headers = {"content-type": "text/html"}

        def json(self):
            return {}

        def raise_for_status(self):
            pass

    return FakeResponse()


# ---------------------------------------------------------------------------
# keywords
# ---------------------------------------------------------------------------


class TestKeywords:
    def test_parse_none_uses_defaults(self):
        assert parse_keywords(None) == expand_keywords(DEFAULT_KEYWORDS)

    def test_parse_empty_tuple_uses_defaults(self):
        assert parse_keywords(()) == expand_keywords(DEFAULT_KEYWORDS)

    def test_parse_comma_separated(self):
        kws = parse_keywords(("free llm api, free model",))
        assert "free llm api" in kws
        assert "free model" in kws

    def test_parse_dedupe_case_insensitive(self):
        kws = parse_keywords(("Free LLM API", "free llm api", "cheap api"))
        assert kws.count("Free LLM API") == 1
        assert "cheap api" in kws

    def test_expand_year_placeholder(self):
        expanded = expand_keywords(["free llm api {year}"])
        assert "{year}" not in expanded[0]
        assert any(ch.isdigit() for ch in expanded[0])

    def test_defaults_have_no_placeholder(self):
        for kw in expand_keywords(DEFAULT_KEYWORDS):
            assert "{year}" not in kw

    def test_scope_keyword_adds_site(self):
        assert scope_keyword("free llm api", "reddit").startswith("site:reddit.com")

    def test_scope_keyword_noop_for_ddg(self):
        assert scope_keyword("free llm api", "duckduckgo") == "free llm api"

    def test_scope_keyword_noop_when_already_scoped(self):
        kw = "site:reddit.com free llm api"
        assert scope_keyword(kw, "reddit") == kw


# ---------------------------------------------------------------------------
# backends — Reddit / Hacker News / DuckDuckGo / GitHub
# ---------------------------------------------------------------------------


def _fake_json_response(payload):
    class FakeResponse:
        status_code = 200
        text = ""
        headers = {"content-type": "application/json"}

        def json(self):
            return payload

        def raise_for_status(self):
            pass

    return FakeResponse()


class TestSearchReddit:
    def test_parses_posts(self, monkeypatch):
        payload = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Free LLM API list",
                            "permalink": "/r/LocalLLaMA/comments/abc/free/",
                            "selftext": "Check out these free providers",
                            "subreddit": "LocalLLaMA",
                        }
                    }
                ]
            }
        }
        monkeypatch.setattr("httpx.get", lambda url, **kw: _fake_json_resp(payload))
        results = search_reddit("free llm api", timeout=1.0)
        assert len(results) == 1
        assert results[0].source == "reddit"
        assert results[0].url.startswith("https://www.reddit.com/r/LocalLLaMA")
        assert results[0].extra["subreddit"] == "LocalLLaMA"

    def test_network_error_raises(self, monkeypatch):
        def fake_get(url, **kw):
            raise httpx.ConnectError("boom")

        monkeypatch.setattr("httpx.get", fake_get)
        with pytest.raises(httpx.HTTPError):
            search_reddit("q", timeout=1.0)


class TestSearchHackerNews:
    def test_parses_hits(self, monkeypatch):
        payload = {
            "hits": [
                {
                    "title": "Show HN: Free LLM API",
                    "url": "https://coolapi.example.com",
                    "story_text": "free tier available",
                    "points": 42,
                    "objectID": "1",
                },
                {"title": "No URL story", "url": None, "objectID": "2"},
                {"title": None, "url": "https://x.com"},
            ]
        }
        monkeypatch.setattr("httpx.get", lambda url, **kw: _fake_json_resp(payload))
        results = search_hackernews("free llm", timeout=1.0)
        assert len(results) == 2
        assert results[0].url == "https://coolapi.example.com"
        assert results[1].url == "https://news.ycombinator.com/item?id=2"


class TestSearchDuckDuckGo:
    def test_parses_links_and_strips_html(self, monkeypatch):
        html = (
            '<a rel="nofollow" class="result__a" href="https://freeprovider.io">Free <b>LLM</b> API</a>'
            '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fanother.ai%2Fv1">Another</a>'
        )

        class FakeResponse:
            status_code = 200
            text = html
            headers = {"content-type": "text/html"}

            def json(self):
                return {}

            def raise_for_status(self):
                pass

        monkeypatch.setattr("httpx.post", lambda url, **kw: FakeResponse())
        results = search_duckduckgo("free llm api", timeout=1.0)
        assert len(results) == 2
        assert results[0].url == "https://freeprovider.io"
        assert results[0].title == "Free LLM API"
        assert results[1].url == "https://another.ai/v1"  # redirect được giải mã

    def test_ddg_challenge_page_returns_empty(self, monkeypatch):
        """Trang anti-bot challenge (không có link kết quả) → trả về [] thay vì crash."""
        html_challenge = "<html><body>anomaly detected</body></html>"
        monkeypatch.setattr("httpx.post", lambda url, **kw: _fake_html_resp(html_challenge))
        results = search_duckduckgo("free llm api", timeout=1.0)
        assert results == []

    def test_resolves_ddg_redirect(self):
        assert (
            _resolve_ddg_url("//duckduckgo.com/l/?uddg=https%3A%2F%2Freal.com%2Fv1&rut=abc")
            == "https://real.com/v1"
        )
        assert _resolve_ddg_url("https://direct.com") == "https://direct.com"


class TestSearchGithub:
    def test_parses_repos(self, monkeypatch):
        payload = {
            "items": [
                {
                    "full_name": "user/free-llm-apis",
                    "html_url": "https://github.com/user/free-llm-apis",
                    "description": "List of free LLM APIs",
                    "stargazers_count": 100,
                }
            ]
        }
        monkeypatch.setattr("httpx.get", lambda url, **kw: _fake_json_resp(payload))
        results = search_github("free llm api", timeout=1.0)
        assert len(results) == 1
        assert results[0].source == "github"
        assert results[0].extra["stars"] == 100


class TestParseSources:
    def test_none_returns_all(self):
        assert parse_sources(None) == AVAILABLE_SOURCES

    def test_empty_string_returns_all(self):
        assert parse_sources("  ") == AVAILABLE_SOURCES

    def test_aliases(self):
        assert parse_sources("hn,ddg,gh") == ["hackernews", "duckduckgo", "github"]

    def test_google_alias(self):
        assert parse_sources("g") == ["google"]

    def test_invalid_names_skipped(self):
        assert parse_sources("reddit,facebook") == ["reddit"]


class TestRunSearch:
    def test_dedupes_by_url(self):
        import src.discovery.websearch.backends as b

        def backend_a(q, n, t):
            return [
                SearchResult(title="A1", url="https://a.com", source="reddit"),
                SearchResult(title="A2", url="https://a2.com", source="reddit"),
            ]

        def backend_b(q, n, t):
            return [SearchResult(title="B1", url="https://a.com", source="github")]  # trùng A1

        saved = dict(b.SEARCH_BACKENDS)
        b.SEARCH_BACKENDS.clear()
        b.SEARCH_BACKENDS.update({"reddit": backend_a, "github": backend_b})
        try:
            results = run_search(["kw"], sources=["reddit", "github"], max_results=5, timeout=1.0)
        finally:
            b.SEARCH_BACKENDS.clear()
            b.SEARCH_BACKENDS.update(saved)

        assert len(results) == 2
        assert results[0].source == "reddit"

    def test_failing_source_does_not_crash(self, monkeypatch):
        import src.discovery.websearch.backends as b

        def broken(q, n, t):
            raise RuntimeError("boom")

        def ok(q, n, t):
            return [b.SearchResult(title="ok", url="https://ok.com", source="github")]


# ---------------------------------------------------------------------------
# deep_search — dedupe + orchestration
# ---------------------------------------------------------------------------


class TestDedupeProviders:
    def test_removes_duplicate_base_url(self):
        p1 = Provider(name="A", base_url="https://api.x.com/v1")
        p2 = Provider(name="X Again", base_url="https://api.x.com/v1")
        assert dedupe_providers([p1, p2]) == [p1]

    def test_removes_duplicate_name_case_insensitive(self):
        p1 = Provider(name="Same", base_url="https://a.com/v1")
        p2 = Provider(name="api", base_url="https://b.com/v1")
        p3 = Provider(name="API", base_url="https://c.com/v1")
        result = dedupe_providers([p1, p2, p3])
        assert len(result) == 2
        assert {p.name for p in result} == {"Same", "api"}

    def test_existing_registry_providers_filtered(self):
        known = Provider(name="Groq", base_url="https://api.groq.com/openai/v1")
        new_p = Provider(name="Groq Clone", base_url="https://api.groq.com/openai/v1")
        result = dedupe_providers([new_p], existing=[known])
        assert result == []


class TestRunDeepSearch:
    def _patch_pipeline(self, monkeypatch, search_results, heuristic_providers, ai_providers=None):
        import src.discovery.websearch.deep_search as ds

        monkeypatch.setattr(ds, "run_search", lambda *a, **kw: search_results)
        monkeypatch.setattr(ds, "extract_heuristic", lambda results: heuristic_providers)
        monkeypatch.setattr(
            ds, "collect_page_contexts", lambda results, max_pages=5, timeout=15.0: []
        )
        monkeypatch.setattr(
            "src.discovery.websearch.deep_search.extract_with_ai",
            lambda ctx, res, kw, cfg: ai_providers or [],
        )
        return ds

    def test_heuristic_mode_returns_web_discovered(self, monkeypatch):
        new_provider = Provider(
            name="BrandNew",
            base_url="https://api.brandnew.ai/v1",
            tags=["web-discovered"],
        )
        self._patch_pipeline(
            monkeypatch,
            search_results=[_result("https://blog.com/x")],
            heuristic_providers=[new_provider],
        )
        found = run_deep_search(keywords=["free llm api"], mode="heuristic", timeout=1.0)
        assert new_provider in found
        assert "deep-search" in found[0].tags

    def test_filters_known_registry_providers(self, monkeypatch):

        clone = Provider(name="Groq", base_url="https://api.groq.com/openai/v1")
        self._patch_pipeline(
            monkeypatch,
            search_results=[_result("https://x.com")],
            heuristic_providers=[clone],
        )
        found = run_deep_search(keywords=["k"], mode="heuristic")
        assert clone not in found

    def test_ai_mode_unconfigured_falls_back_to_heuristic(self, monkeypatch):
        from src.config import AIConfig

        new_provider = Provider(name="HeuristicOnly", base_url="https://api.h-only.com/v1")
        self._patch_pipeline(
            monkeypatch,
            search_results=[_result("https://blog.com/x")],
            heuristic_providers=[new_provider],
        )
        cfg = AIConfig(AI_PROVIDER_BASE_URL="", AI_API_KEY="", AI_MODEL="m")
        found = run_deep_search(keywords=["kw"], mode="ai", ai_config=cfg)
        assert new_provider in found

    def test_ai_mode_error_falls_back_to_heuristic(self, monkeypatch):
        from src.config import AIConfig

        new_provider = Provider(name="Fallback", base_url="https://api.fallback.ai/v1")

        import src.discovery.websearch.deep_search as ds

        monkeypatch.setattr(ds, "run_search", lambda *a, **kw: [_result("https://b.com")])
        monkeypatch.setattr(ds, "collect_page_contexts", lambda *a, **kw: [])

        def exploding_ai(ctx, res, kw, cfg):
            raise RuntimeError("LLM down")

        monkeypatch.setattr(ds, "extract_with_ai", exploding_ai)
        monkeypatch.setattr(ds, "extract_heuristic", lambda results: [new_provider])
        cfg = AIConfig(AI_PROVIDER_BASE_URL="https://x", AI_API_KEY="k", AI_MODEL="m")
        found = run_deep_search(keywords=["k"], mode="ai", ai_config=cfg)
        assert new_provider in found

    def test_ai_mode_success_combines_with_heuristic(self, monkeypatch):
        from src.config import AIConfig

        ai_p = Provider(
            name="AIFound", base_url="https://api.aifound.ai/v1", tags=["web-discovered"]
        )
        heur_p = Provider(name="HeurFound", base_url="https://api.heur.ai/v1")
        import src.discovery.websearch.deep_search as ds

        monkeypatch.setattr(ds, "run_search", lambda *a, **kw: [_result("https://b.com")])
        monkeypatch.setattr(ds, "collect_page_contexts", lambda *a, **kw: [])
        monkeypatch.setattr(ds, "extract_with_ai", lambda ctx, res, kw, cfg: [ai_p])
        monkeypatch.setattr(ds, "extract_heuristic", lambda results: [heur_p])
        cfg = AIConfig(AI_PROVIDER_BASE_URL="https://x", AI_API_KEY="k", AI_MODEL="m")
        found = run_deep_search(keywords=["k"], mode="ai", ai_config=cfg)
        names = [p.name for p in found]
        assert "AIFound" in names
        assert "HeurFound" in names


# ---------------------------------------------------------------------------
# extractor — heuristic
# ---------------------------------------------------------------------------


class TestExtractorHelpers:
    def test_domain_of(self):
        assert _domain_of("https://api.groq.com/openai/v1/models") == "api.groq.com"
        assert _domain_of("https://www.example.com/x") == "example.com"
        assert _domain_of("not a url") == ""

    def test_is_blocked_social_domains(self):
        assert _is_blocked("https://www.reddit.com/r/foo") is True
        assert _is_blocked("https://facebook.com/page") is True
        assert _is_blocked("https://news.ycombinator.com/item?id=1") is True

    def test_is_blocked_allows_unknown_domains(self):
        assert _is_blocked("https://api.coolprovider.ai/v1") is False

    def test_provider_name_from_host(self):
        assert _provider_name_from_host("api.groq.com") == "Groq"
        assert _provider_name_from_host("openrouter.ai") == "Openrouter"


class TestExtractHeuristic:
    def test_finds_api_url_in_snippet(self):
        results = [
            _result(
                url="https://blog.example.com/free-apis",
                title="Best free LLM APIs",
                snippet="Try https://api.newprovider.ai/v1 for free models",
            )
        ]
        providers = extract_heuristic(results)
        assert len(providers) == 1
        assert providers[0].base_url == "https://api.newprovider.ai/v1"
        assert providers[0].website == "https://api.newprovider.ai"
        assert "web-discovered" in providers[0].tags

    def test_skips_blocked_domains(self):
        results = [_result(url="https://api.reddit.com/v1", snippet="https://api.reddit.com/v1")]
        assert extract_heuristic(results) == []

    def test_dedupes_by_domain(self):
        results = [
            _result(url="https://a.com", snippet="try https://api.x.ai/v1/chat"),
            _result(url="https://b.com", snippet="also https://api.x.ai/v1/models"),
        ]
        providers = extract_heuristic(results)
        assert len(providers) == 1
        assert providers[0].base_url == "https://api.x.ai/v1/chat"

    def test_no_api_url_found_returns_empty(self):
        results = [_result(url="https://plain-blog.com/post", title="just a blog")]
        assert extract_heuristic(results) == []

    def test_never_fabricates_base_url(self):
        """Không tìm thấy endpoint rõ ràng → KHÔNG bịa base_url từ domain."""
        results = [_result(url="https://mystery-provider.com", title="free api here")]
        assert extract_heuristic(results) == []


class TestFetchPageText:
    def test_returns_text_for_html(self, monkeypatch):
        monkeypatch.setattr("httpx.get", lambda url, **kw: _fake_html_resp("<html>hello</html>"))
        assert fetch_page_text("https://x.com", timeout=1.0) == "<html>hello</html>"

    def test_skips_binary_content_type(self, monkeypatch):
        def fake_get(url, **kw):
            resp = _fake_html_resp("binary")
            resp.headers = {"content-type": "application/octet-stream"}
            return resp

        monkeypatch.setattr("httpx.get", fake_get)
        assert fetch_page_text("https://x.com/file", timeout=1.0) == ""

    def test_error_returns_empty(self, monkeypatch):
        def fake_get(url, **kw):
            raise httpx.ConnectError("nope")

        monkeypatch.setattr("httpx.get", fake_get)
        assert fetch_page_text("https://dead.example.com", timeout=1.0) == ""


class TestIsBlocked:
    def test_subdomain_blocked(self):
        assert _is_blocked("https://old.reddit.com/r/x") is True

    def test_similar_domain_not_blocked(self):
        assert _is_blocked("https://reddittracker.com") is False


# ---------------------------------------------------------------------------
# extractor — AI mode
# ---------------------------------------------------------------------------


class TestExtractWithAI:
    def _make_config(self):
        from src.config import AIConfig

        return AIConfig(
            AI_PROVIDER_BASE_URL="https://ai.test.com/v1",
            AI_API_KEY="sk-test",
            AI_MODEL="test-model",
            AI_TIMEOUT=5,
        )

    def _ai_response(self, providers_json: str):
        class FakeResponse:
            status_code = 200
            text = ""
            headers = {"content-type": "application/json"}

            def json(self):
                return {"choices": [{"message": {"content": providers_json}}]}

            def raise_for_status(self):
                pass

        return FakeResponse()

    def test_success_extracts_providers_with_web_tag(self, monkeypatch):
        from src.discovery.websearch.extractor import extract_with_ai

        raw = """
        {"providers": [{"name": "NewAI", "base_url": "https://api.newai.dev/v1",
          "website": "https://newai.dev", "description": "free tier",
          "api_style": "openai", "auth_required": true,
          "tags": ["fresh"], "free_models": [{"id": "m1", "name": "M1"}]}]}
        """

        def fake_post(url, **kw):
            return self._ai_response(raw)

        monkeypatch.setattr("httpx.post", fake_post)
        providers = extract_with_ai(
            [], [_result("https://blog.com/x")], ["kw"], self._make_config()
        )
        assert len(providers) == 1
        assert providers[0].name == "NewAI"
        assert "web-discovered" in providers[0].tags
        assert "ai-discovered" not in providers[0].tags
        assert "deep-search" in providers[0].tags

    def test_401_raises_runtime_error(self, monkeypatch):
        from src.discovery.websearch.extractor import extract_with_ai

        def fake_post(url, **kw):
            class Resp:
                status_code = 401

            return Resp()

        monkeypatch.setattr("httpx.post", fake_post)
        with pytest.raises(RuntimeError, match="401"):
            extract_with_ai([], [_result("https://b.com")], ["kw"], self._make_config())

    def test_invalid_json_raises(self, monkeypatch):
        from src.discovery.websearch.extractor import extract_with_ai

        def fake_post(url, **kw):
            return self._ai_response("không phải json {")

        monkeypatch.setattr("httpx.post", fake_post)
        with pytest.raises(ValueError):
            extract_with_ai([], [_result("https://b.com")], ["kw"], self._make_config())

    def test_empty_input_returns_empty(self):
        from src.discovery.websearch.extractor import extract_with_ai

        assert extract_with_ai([], [], ["kw"], self._make_config()) == []


class TestCollectPageContexts:
    def test_respects_max_pages_and_skips_blocked(self, monkeypatch):
        from src.discovery.websearch.extractor import collect_page_contexts

        results = [
            _result("https://social.reddit.com/post"),  # blocked → bỏ
            _result("https://page1.com/a"),
            _result("https://page2.com/b"),
            _result("https://page3.com/c"),
        ]
        monkeypatch.setattr(
            "src.discovery.websearch.extractor.fetch_page_text",
            lambda url, timeout=15.0, max_chars=6000: f"text of {url}",
        )
        contexts = collect_page_contexts(results, max_pages=2)
        assert len(contexts) == 2
        assert contexts[0][0] == "https://page1.com/a"

    def test_skips_failed_pages(self, monkeypatch):
        from src.discovery.websearch.extractor import collect_page_contexts

        results = [_result("https://dead.com/x"), _result("https://alive.com/y")]
        monkeypatch.setattr(
            "src.discovery.websearch.extractor.fetch_page_text",
            lambda url, timeout=15.0, max_chars=6000: "" if "dead" in url else f"text {url}",
        )
        contexts = collect_page_contexts(results, max_pages=5)
        assert len(contexts) == 1
        assert contexts[0][0] == "https://alive.com/y"


# ---------------------------------------------------------------------------
# backends — retry + http_get edge cases
# ---------------------------------------------------------------------------


class TestHttpGetRetry:
    def test_retries_on_503_then_succeeds(self, monkeypatch):
        from src.discovery.websearch.backends import _http_get

        calls = {"n": 0}

        class Resp:
            status_code = 200
            text = ""
            headers = {"content-type": "application/json"}

            def json(self):
                return {}

            def raise_for_status(self):
                pass

        def fake_get(url, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                resp = httpx.Response(503, request=httpx.Request("GET", url))
                raise httpx.HTTPStatusError("err", request=resp.request, response=resp)
            return Resp()

        monkeypatch.setattr("httpx.get", fake_get)
        monkeypatch.setattr("src.discovery.websearch.backends.time.sleep", lambda s: None)
        assert _http_get("https://x.com").status_code == 200
        assert calls["n"] == 2

    def test_404_raises_immediately(self, monkeypatch):
        from src.discovery.websearch.backends import _http_get

        def fake_get(url, **kw):
            resp = httpx.Response(404, request=httpx.Request("GET", url))
            raise httpx.HTTPStatusError("err", request=resp.request, response=resp)

        monkeypatch.setattr("httpx.get", fake_get)
        with pytest.raises(httpx.HTTPStatusError):
            _http_get("https://x.com")


class TestFetchPageTextJson:
    def test_accepts_json_content_type(self, monkeypatch):
        resp = _fake_json_resp({"ok": True})
        resp.text = '{"ok": true}'
        monkeypatch.setattr("httpx.get", lambda url, **kw: resp)
        assert fetch_page_text("https://api.com/data", timeout=1.0) == '{"ok": true}'


class TestCollectPageContextsDeep:
    def test_crawls_second_level_links(self, monkeypatch):
        """Deep crawl: trang cấp 1 chứa link con → link con cũng được fetch."""
        from src.discovery.websearch.extractor import collect_page_contexts_deep

        pages = {
            "https://community.id/post": (
                '<html>Free keys at <a href="https://community.id/bansos-page">bansos</a></html>'
            ),
            "https://community.id/bansos-page": "<html>key list here api https://api.x.ai/v1</html>",
        }

        def fake_fetch(url, timeout=15.0, max_chars=6000):
            return pages.get(url, "")

        monkeypatch.setattr(
            "src.discovery.websearch.extractor.fetch_page_text", fake_fetch
        )
        results = [_result("https://community.id/post")]
        contexts = collect_page_contexts_deep(results, max_pages=5, timeout=1.0)
        urls = [u for u, _ in contexts]
        assert "https://community.id/post" in urls
        assert "https://community.id/bansos-page" in urls  # cấp 2 được follow

    def test_respects_max_pages_budget(self, monkeypatch):
        """Tổng số trang fetch không vượt max_pages dù link con nhiều."""
        from src.discovery.websearch.extractor import collect_page_contexts_deep

        pages = {}
        for i in range(10):
            pages[f"https://site.com/p{i}"] = (
                f'<html><a href="https://site.com/p{i + 1}">free api next</a></html>'
            )

        monkeypatch.setattr(
            "src.discovery.websearch.extractor.fetch_page_text",
            lambda url, timeout=15.0, max_chars=6000: pages.get(url, ""),
        )
        results = [_result("https://site.com/p0")]
        contexts = collect_page_contexts_deep(results, max_pages=3, timeout=1.0)
        assert len(contexts) <= 3

    def test_blocked_links_not_followed(self, monkeypatch):
        """Link con trỏ tới social/blocked domain không bị follow."""
        from src.discovery.websearch.extractor import collect_page_contexts_deep

        fetched = []
        pages = {
            "https://blog.com/post": (
                '<html><a href="https://www.reddit.com/r/x">reddit</a>'
                '<a href="https://blog.com/real">free api</a></html>'
            ),
            "https://blog.com/real": "<html>content</html>",
        }

        def fake_fetch(url, timeout=15.0, max_chars=6000):
            fetched.append(url)
            return pages.get(url, "")

        monkeypatch.setattr(
            "src.discovery.websearch.extractor.fetch_page_text", fake_fetch
        )
        contexts = collect_page_contexts_deep([_result("https://blog.com/post")], max_pages=5)
        assert not any("reddit.com" in u for u in fetched)
        assert "https://blog.com/real" in [u for u, _ in contexts]

    def test_external_link_without_hint_not_followed(self, monkeypatch):
        """Link ngoài domain, không có hint free/api → không follow (chống lan truyền)."""
        from src.discovery.websearch.extractor import collect_page_contexts_deep

        pages = {
            "https://blog.com/post": (
                '<html><a href="https://random-site.com/page">click here</a></html>'
            )
        }
        monkeypatch.setattr(
            "src.discovery.websearch.extractor.fetch_page_text",
            lambda url, timeout=15.0, max_chars=6000: pages.get(url, ""),
        )
        contexts = collect_page_contexts_deep([_result("https://blog.com/post")], max_pages=5)
        assert [u for u, _ in contexts] == ["https://blog.com/post"]  # chỉ trang gốc


# ---------------------------------------------------------------------------
# CLI discover-web
# ---------------------------------------------------------------------------


class TestDiscoverWebCLI:
    def _state_opt(self, tmp_path):
        return ["--state", str(tmp_path / "scan_state.json")]

    def test_requires_no_key_and_reports_empty(self, runner, monkeypatch, tmp_path):
        import src.cli.main as m

        monkeypatch.setattr(m, "run_deep_search", lambda **kw: [])
        result = runner.invoke(m.cli, ["discover-web", *self._state_opt(tmp_path)])
        assert result.exit_code == 0
        assert "chưa tìm thấy provider mới nào" in result.output

    def test_shows_found_providers(self, runner, monkeypatch, tmp_path):
        import src.cli.main as m

        found = [
            Provider(
                name="BrandNew",
                base_url="https://api.brandnew.ai/v1",
                tags=["web-discovered", "deep-search"],
            )
        ]
        monkeypatch.setattr(m, "run_deep_search", lambda **kw: found)
        result = runner.invoke(
            m.cli, ["discover-web", "--mode", "heuristic", *self._state_opt(tmp_path)]
        )
        assert result.exit_code == 0
        assert "BrandNew" in result.output

    def test_custom_keywords_passed_to_pipeline(self, runner, monkeypatch, tmp_path):
        import src.cli.main as m

        captured = {}

        def fake_run(**kw):
            captured.update(kw)
            return []

        monkeypatch.setattr(m, "run_deep_search", fake_run)
        runner.invoke(
            m.cli, ["discover-web", "-k", "free llm api, cheap api", *self._state_opt(tmp_path)]
        )
        assert "free llm api" in captured["keywords"]
        assert "cheap api" in captured["keywords"]

    def test_sources_filter(self, runner, monkeypatch, tmp_path):
        import src.cli.main as m

        captured = {}

        def fake_run(**kw):
            captured.update(kw)
            return []

        monkeypatch.setattr(m, "run_deep_search", fake_run)
        runner.invoke(m.cli, ["discover-web", "--sources", "reddit,hn", *self._state_opt(tmp_path)])
        assert captured["sources"] == ["reddit", "hackernews"]

    def test_pipeline_error_exits_1(self, runner, monkeypatch, tmp_path):
        import src.cli.main as m

        def boom(**kw):
            raise RuntimeError("network down")

        monkeypatch.setattr(m, "run_deep_search", boom)
        result = runner.invoke(m.cli, ["discover-web", *self._state_opt(tmp_path)])
        assert result.exit_code == 1
        assert "Lỗi deep search" in result.output

    def test_output_saves_file(self, runner, monkeypatch, tmp_path):
        import src.cli.main as m

        found = [Provider(name="BrandNew", base_url="https://api.brandnew.ai/v1")]
        monkeypatch.setattr(m, "run_deep_search", lambda **kw: found)
        out = tmp_path / "web_providers.json"
        result = runner.invoke(
            m.cli, ["discover-web", "--output", str(out), *self._state_opt(tmp_path)]
        )
        assert result.exit_code == 0
        assert out.exists()

    def test_resume_accumulates_providers(self, runner, monkeypatch, tmp_path):
        """Lần chạy 2 (resume) phải gộp provider của lần chạy 1 + tìm thêm cái mới."""
        import src.cli.main as m

        state_file = tmp_path / "scan_state.json"
        run1 = [Provider(name="First", base_url="https://api.first.ai/v1")]
        run2 = [Provider(name="Second", base_url="https://api.second.ai/v1")]
        monkeypatch.setattr(m, "run_deep_search", lambda **kw: run1)
        runner.invoke(m.cli, ["discover-web", "--state", str(state_file)])
        monkeypatch.setattr(m, "run_deep_search", lambda **kw: run2)
        out = tmp_path / "out.json"
        result = runner.invoke(m.cli, ["discover-web", "--state", str(state_file), "-o", str(out)])
        assert result.exit_code == 0
        assert "Second" in result.output

        data = json.loads(out.read_text())
        names = [p["name"] for p in data["providers"]]
        assert "First" in names and "Second" in names  # tích luỹ cả 2 lần chạy

    def test_resume_skips_used_keywords(self, runner, monkeypatch, tmp_path):
        """Lần chạy 2 (resume, không -k) phải xoay sang keyword CHƯA dùng."""
        import src.cli.main as m

        state_file = tmp_path / "scan_state.json"
        captured_runs = []

        def fake_run(**kw):
            captured_runs.append(list(kw["keywords"]))
            return []

        monkeypatch.setattr(m, "run_deep_search", fake_run)
        runner.invoke(m.cli, ["discover-web", "--state", str(state_file)])
        runner.invoke(m.cli, ["discover-web", "--state", str(state_file)])

        assert len(captured_runs) == 2
        kw1, kw2 = set(captured_runs[0]), set(captured_runs[1])
        assert kw1 and kw2
        assert kw1.isdisjoint(kw2)  # không lặp lại keyword đã dùng

    def test_fresh_ignores_state(self, runner, monkeypatch, tmp_path):
        """--fresh: bỏ trạng thái cũ, dùng lại từ đầu pool keyword."""
        import src.cli.main as m

        state_file = tmp_path / "scan_state.json"
        captured_runs = []

        def fake_run(**kw):
            captured_runs.append(list(kw["keywords"]))
            return []

        monkeypatch.setattr(m, "run_deep_search", fake_run)
        runner.invoke(m.cli, ["discover-web", "--state", str(state_file)])
        runner.invoke(m.cli, ["discover-web", "--fresh", "--state", str(state_file)])

        assert set(captured_runs[0]) == set(captured_runs[1])

    def test_state_saved_after_run(self, runner, monkeypatch, tmp_path):
        """Sau mỗi lần quét, file trạng thái phải được lưu (kể cả URL đã xử lý)."""
        import src.cli.main as m

        state_file = tmp_path / "scan_state.json"
        found = [Provider(name="BrandNew", base_url="https://api.brandnew.ai/v1")]

        def fake_run(**kw):
            # Mô phỏng pipeline thật: gọi on_results với các URL kết quả search
            if kw.get("on_results"):
                kw["on_results"](
                    [SearchResult(title="t", url="https://example.com/post-1", source="reddit")]
                )
            return found

        monkeypatch.setattr(m, "run_deep_search", fake_run)
        result = runner.invoke(m.cli, ["discover-web", "--state", str(state_file)])
        assert result.exit_code == 0
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["total_providers"] == 1
        assert data["seen_urls"] == ["https://example.com/post-1"]

    def test_corrupted_state_resets_gracefully(self, runner, monkeypatch, tmp_path):
        """File trạng thái hỏng → reset về rỗng, pipeline vẫn chạy bình thường."""
        import src.cli.main as m

        state_file = tmp_path / "scan_state.json"
        state_file.write_text("{corrupted json!", encoding="utf-8")
        found = [Provider(name="BrandNew", base_url="https://api.brandnew.ai/v1")]
        monkeypatch.setattr(m, "run_deep_search", lambda **kw: found)
        result = runner.invoke(m.cli, ["discover-web", "--state", str(state_file)])
        assert result.exit_code == 0
        assert "BrandNew" in result.output

    def test_default_mode_is_ai(self, runner, monkeypatch, tmp_path):
        """Không truyền --mode → mặc định dùng 'ai' (AI tham gia giai đoạn tìm)."""
        import src.cli.main as m

        captured = {}

        def fake_run(**kw):
            captured.update(kw)
            return []

        monkeypatch.setattr(m, "run_deep_search", fake_run)
        result = runner.invoke(m.cli, ["discover-web", *self._state_opt(tmp_path)])
        assert result.exit_code == 0
        assert captured["mode"] == "ai"

    def test_no_dedup_disables_url_exclusion(self, runner, monkeypatch, tmp_path):
        """--no-dedup → exclude_urls=None: URL đã xem được quét lại."""
        import src.cli.main as m

        state_file = tmp_path / "scan_state.json"
        # Lần 1: đánh dấu 1 URL đã xem
        seen = {"https://example.com/post-1"}

        def fake_run_1(**kw):
            assert kw["exclude_urls"] == seen or kw["exclude_urls"] == set()
            if kw.get("on_results"):
                kw["on_results"](
                    [SearchResult(title="t", url="https://example.com/post-1", source="reddit")]
                )
            return []

        monkeypatch.setattr(m, "run_deep_search", fake_run_1)
        runner.invoke(m.cli, ["discover-web", "--state", str(state_file)])

        # Lần 2 với --no-dedup: exclude_urls phải là None (không loại URL cũ)
        captured = {}

        def fake_run_2(**kw):
            captured.update(kw)
            return []

        monkeypatch.setattr(m, "run_deep_search", fake_run_2)
        result = runner.invoke(
            m.cli, ["discover-web", "--no-dedup", "--state", str(state_file)]
        )
        assert result.exit_code == 0
        assert captured["exclude_urls"] is None

    def test_rerun_same_keyword_updates_existing_provider(self, runner, monkeypatch, tmp_path):
        """Chạy lại cùng keyword: provider tìm lại phải được CẬP NHẬT info, không rỗng."""
        import src.cli.main as m

        state_file = tmp_path / "scan_state.json"
        # Lần 1: tìm thấy provider chưa có model
        run1 = [Provider(name="Fresh", base_url="https://api.fresh.ai/v1", models=[])]
        monkeypatch.setattr(m, "run_deep_search", lambda **kw: run1)
        runner.invoke(m.cli, ["discover-web", "-k", "free llm api", "--state", str(state_file)])

        # Lần 2: CÙNG keyword, AI trích xuất được model thật → phải báo "CẬP NHẬT"
        run2 = [
            Provider(
                name="Fresh",
                base_url="https://api.fresh.ai/v1",
                models=[{"id": "real-model", "name": "Real", "is_free": True}],
            )
        ]
        monkeypatch.setattr(m, "run_deep_search", lambda **kw: run2)
        result = runner.invoke(
            m.cli, ["discover-web", "-k", "free llm api", "--state", str(state_file)]
        )
        assert result.exit_code == 0
        assert "CẬP NHẬT" in result.output  # không rỗng — có provider được cập nhật
        state = json.loads(state_file.read_text())
        saved_models = state["providers"][0]["models"]
        assert [mm["id"] for mm in saved_models] == ["real-model"]

    def test_run_history_saved_after_scan(self, runner, monkeypatch, tmp_path):
        """Sau mỗi lần scan, run_history (timestamp) phải được ghi vào file trạng thái."""
        import src.cli.main as m

        state_file = tmp_path / "scan_state.json"
        found = [Provider(name="BrandNew", base_url="https://api.brandnew.ai/v1")]
        monkeypatch.setattr(m, "run_deep_search", lambda **kw: found)
        result = runner.invoke(m.cli, ["discover-web", "--state", str(state_file)])
        assert result.exit_code == 0
        data = json.loads(state_file.read_text())
        assert len(data["run_history"]) == 1
        entry = data["run_history"][0]
        assert entry["new_providers"] == 1
        assert "run_at" in entry
        assert "Lần scan này" in result.output

    def test_deep_search_default_on_passes_to_pipeline(self, runner, monkeypatch, tmp_path):
        """Không truyền --deep-search → mặc định deep=True được truyền vào pipeline."""
        import src.cli.main as m

        captured = {}

        def fake_run(**kw):
            captured.update(kw)
            return []

        monkeypatch.setattr(m, "run_deep_search", fake_run)
        result = runner.invoke(m.cli, ["discover-web", *self._state_opt(tmp_path)])
        assert result.exit_code == 0
        assert captured.get("deep") is True

    def test_no_deep_search_disables_deep_crawl(self, runner, monkeypatch, tmp_path):
        """--no-deep-search → deep=False: chỉ fetch trang kết quả (không follow link con)."""
        import src.cli.main as m

        captured = {}

        def fake_run(**kw):
            captured.update(kw)
            return []

        monkeypatch.setattr(m, "run_deep_search", fake_run)
        result = runner.invoke(m.cli, ["discover-web", "--no-deep-search", *self._state_opt(tmp_path)])
        assert result.exit_code == 0
        assert captured.get("deep") is False

    def test_social_source_available(self, runner, monkeypatch, tmp_path):
        """--sources social chạy được (X/Threads/Instagram site-scoped)."""
        import src.cli.main as m

        captured = {}

        def fake_run(**kw):
            captured.update(kw)
            return []

        monkeypatch.setattr(m, "run_deep_search", fake_run)
        result = runner.invoke(
            m.cli, ["discover-web", "--sources", "social", "-k", "free llm api", *self._state_opt(tmp_path)]
        )
        assert result.exit_code == 0
        assert captured.get("sources") == ["social"]


# ---------------------------------------------------------------------------
# backends — shared keys (Crown AI + LMSpeed)
# ---------------------------------------------------------------------------


class TestSharedKeysSource:
    def test_crown_status_parses_alive_models(self, monkeypatch):
        from src.discovery.websearch.backends import search_shared_keys

        payload = {
            "ok": True,
            "data": {
                "pool": {"keys_checked": 10, "alive_keys": 8},
                "models": [
                    {"id": "zai-org/GLM-5.3-Flash", "alive": True, "latency_ms": 206},
                    {"id": "dead-model", "alive": False},
                    {"id": "deepseek-ai/DeepSeek-V4-Flash-0731", "alive": True},
                ],
            },
        }

        class FakeResp:
            status_code = 200
            headers = {"content-type": "application/json"}

            def json(self):
                return payload

            def raise_for_status(self):
                pass

        monkeypatch.setattr("httpx.get", lambda url, **kw: FakeResp())
        results = search_shared_keys("any", max_results=10, timeout=1.0)
        crown = [r for r in results if "Crown AI" in r.title]
        assert len(crown) == 1
        assert crown[0].source == "shared_keys"
        assert "https://crown.ai.id/v1" in crown[0].snippet
        assert "zai-org/GLM-5.3-Flash" in crown[0].snippet
        assert "dead-model" not in crown[0].snippet  # model chết bị lọc

    def test_lmspeed_providers_parsed_and_deduped(self, monkeypatch):
        from src.discovery.websearch.backends import fetch_lmspeed_shared_keys

        html = (
            '<a href="/provider/nightrouter">NightRouter</a>'
            '<a href="https://lmspeed.net/provider/nightrouter">dup</a>'
            '<a href="/provider/agnes-ai">Agnes AI</a>'
            # RSC payload nhúng baseUrl thật
            'baseUrl:"https://api.nightrouter.ai/v1"'
        )
        monkeypatch.setattr("httpx.get", lambda url, **kw: _fake_html_resp(html))
        results = fetch_lmspeed_shared_keys(timeout=1.0)
        base_urls = [r for r in results if r.url.startswith("https://api.")]
        providers = [r for r in results if "/provider/" in r.url]
        assert len(base_urls) == 1
        assert base_urls[0].url == "https://api.nightrouter.ai/v1"
        assert len(providers) == 2  # nightrouter (dup relative/absolute → 1) + agnes-ai
        assert "Nightrouter" in providers[0].title or "Nightrouter" in providers[1].title
        assert all(r.source == "shared_keys" for r in results)

    def test_both_sources_failing_returns_empty_gracefully(self, monkeypatch):
        from src.discovery.websearch.backends import search_shared_keys

        def fake_get(url, **kw):
            raise httpx.ConnectError("down")

        monkeypatch.setattr("httpx.get", fake_get)
        results = search_shared_keys("q", max_results=10, timeout=1.0)
        assert results == []

    def test_crown_bansos_page_parsed(self, monkeypatch):
        """Trang crown.ai.id/bansos phải được scrape — endpoint /v1 trong HTML."""
        from src.discovery.websearch.backends import fetch_crown_bansos

        html = (
            '<html>Ambil key gratis di <a href="https://api.example-bansos.ai/v1">link</a>'
            ' atau gunakan https://api.other-pool.id/v1/chat/completions</html>'
        )
        monkeypatch.setattr("httpx.get", lambda url, **kw: _fake_html_resp(html))
        results = fetch_crown_bansos(timeout=1.0)
        urls = {r.url for r in results}
        assert "https://api.example-bansos.ai/v1" in urls
        assert "https://api.other-pool.id/v1/chat/completions" in urls
        assert all(r.source == "shared_keys" for r in results)
        assert all("crown.ai.id/bansos" in r.snippet for r in results)

    def test_masb_page_parsed_excludes_self(self, monkeypatch):
        """ai.masb.web.id phải được scrape — endpoint /v1 của provider ngoài, bỏ chính nó."""
        from src.discovery.websearch.backends import fetch_masb_shared_keys

        html = (
            '<html>Provider gratis: <a href="https://api.masb-shared.ai/v1">A</a>'
            " atau https://pool.indo-ai.web.id/v1 — homepage https://ai.masb.web.id/v1</html>"
        )
        monkeypatch.setattr("httpx.get", lambda url, **kw: _fake_html_resp(html))
        results = fetch_masb_shared_keys(timeout=1.0)
        urls = {r.url for r in results}
        assert "https://api.masb-shared.ai/v1" in urls
        assert "https://pool.indo-ai.web.id/v1" in urls
        assert not any("masb.web.id" in u for u in urls)  # chính trang bị loại

    def test_shared_keys_includes_bansos_and_masb(self, monkeypatch):
        """search_shared_keys giờ gồm 4 nguồn: crown status + lmspeed + bansos + masb."""
        from src.discovery.websearch.backends import search_shared_keys

        def fake_get(url, **kw):
            if "crown.ai.id/api/status" in url:
                return _fake_json_resp(
                    {"ok": True, "data": {"pool": {}, "models": [{"id": "m1", "alive": True}]}}
                )
            if "crown.ai.id/bansos" in url:
                return _fake_html_resp('<a href="https://api.bansos-pool.ai/v1">key</a>')
            if "masb.web.id" in url:
                return _fake_html_resp('<a href="https://api.masb-pool.ai/v1">key</a>')
            return _fake_html_resp('baseUrl:"https://api.lmspeed-shared.ai/v1"')

        monkeypatch.setattr("httpx.get", fake_get)
        results = search_shared_keys("q", max_results=50, timeout=1.0)
        urls = {r.url for r in results}
        assert "https://api.bansos-pool.ai/v1" in urls  # bansos được gộp vào
        assert "https://api.masb-pool.ai/v1" in urls  # masb được gộp vào
        assert "https://api.lmspeed-shared.ai/v1" in urls
        assert "https://crown.ai.id" in urls  # status gốc vẫn còn

    def test_shared_keys_not_truncated_by_max_results(self, monkeypatch):
        """Nhiều nguồn shared không bị cắt cụt khi max_results nhỏ."""
        from src.discovery.websearch.backends import search_shared_keys

        def fake_get(url, **kw):
            if "crown.ai.id/api/status" in url:
                return _fake_json_resp({"ok": True, "data": {"models": []}})
            if "lmspeed" in url:
                html = "".join(
                    f'baseUrl:"https://api.s{i}.ai/v1"' for i in range(15)
                )
                return _fake_html_resp(html)
            return _fake_html_resp("")

        monkeypatch.setattr("httpx.get", fake_get)
        results = search_shared_keys("q", max_results=2, timeout=1.0)
        assert len(results) >= 15  # không bị cắt về 2


# ---------------------------------------------------------------------------
# Social backend — X/Threads/Instagram qua Google CSE / DuckDuckGo site-scope
# ---------------------------------------------------------------------------


class TestSocialBackend:
    @pytest.fixture(autouse=True)
    def _clean_google_env(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_CSE_ID", raising=False)
        from src.config import get_google_config

        get_google_config.cache_clear()
        yield
        get_google_config.cache_clear()

    def test_uses_ddg_site_scopes_without_key(self, monkeypatch):
        from src.discovery.websearch.backends import search_social

        captured = []

        def fake_post(url, **kw):
            assert "html.duckduckgo.com" in url
            captured.append(kw.get("data", {}).get("q", ""))
            return _fake_html_resp(
                '<a class="result__a" href="https://x.com/someuser/status/1">free api thread</a>'
            )

        monkeypatch.setattr("httpx.post", fake_post)
        results = search_social("free llm api", max_results=5, timeout=1.0)
        # 3 nền tảng = 3 query, mỗi query có site: scope
        assert len(captured) == 3
        assert any("site:x.com" in q for q in captured)
        assert any("site:threads.net" in q for q in captured)
        assert any("site:instagram.com" in q for q in captured)
        assert results
        assert results[0].source == "social"
        assert results[0].extra["platform"] in {"x", "threads", "instagram"}

    def test_uses_google_cse_when_configured(self, monkeypatch):
        from src.discovery.websearch.backends import search_social

        captured = []

        def fake_get(url, **kw):
            captured.append(url)

            class Resp:
                status_code = 200
                text = ""
                headers = {"content-type": "application/json"}

                def json(self):
                    return {
                        "items": [
                            {"title": "X post", "link": "https://x.com/u/status/2", "snippet": "s"}
                        ]
                    }

                def raise_for_status(self):
                    pass

            return Resp()

        monkeypatch.setattr("httpx.get", fake_get)
        monkeypatch.setenv("GOOGLE_API_KEY", "k")
        monkeypatch.setenv("GOOGLE_CSE_ID", "cx")
        from src.config import get_google_config

        get_google_config.cache_clear()
        results = search_social("free llm api", max_results=5, timeout=1.0)
        assert captured and all("customsearch" in u for u in captured)
        assert results and results[0].url == "https://x.com/u/status/2"
        assert results[0].source == "social"

    def test_one_platform_failing_others_continue(self, monkeypatch):
        """1 nền tảng lỗi → các nền tảng khác vẫn trả kết quả (graceful)."""
        from src.discovery.websearch.backends import search_social

        def fake_post(url, **kw):
            q = kw.get("data", {}).get("q", "")
            if "site:threads.net" in q:
                raise httpx.ConnectError("down")
            return _fake_html_resp(
                '<a class="result__a" href="https://example.com/post">free api</a>'
            )

        monkeypatch.setattr("httpx.post", fake_post)
        results = search_social("free llm api", max_results=5, timeout=1.0)
        assert results  # x + instagram vẫn về kết quả

    def test_dedupes_across_platforms(self, monkeypatch):
        from src.discovery.websearch.backends import search_social

        def fake_post(url, **kw):
            return _fake_html_resp(
                '<a class="result__a" href="https://x.com/u/status/3">same post</a>'
            )

        monkeypatch.setattr("httpx.post", fake_post)
        results = search_social("q", max_results=9, timeout=1.0)
        urls = [r.url for r in results]
        assert len(urls) == len(set(urls))  # URL trùng giữa các platform bị dedupe

    def test_crown_snippet_contains_api_url_for_heuristic(self, monkeypatch):
        """Snippet phải chứa base_url /v1 để heuristic extractor bắt được."""
        from src.discovery.websearch.backends import search_shared_keys
        from src.discovery.websearch.extractor import extract_heuristic

        payload = {
            "data": {
                "pool": {"alive_keys": 5},
                "models": [{"id": "m1", "alive": True}],
            }
        }
        monkeypatch.setattr("httpx.get", lambda url, **kw: _fake_json_resp(payload))
        results = search_shared_keys("q", max_results=5, timeout=1.0)
        providers = extract_heuristic(results)
        crown = [p for p in providers if "crown.ai.id" in p.base_url]
        assert len(crown) == 1
        assert crown[0].base_url == "https://crown.ai.id/v1"


# ---------------------------------------------------------------------------
# Google backend — Custom Search API (có key) / Google News RSS (fallback)
# ---------------------------------------------------------------------------


class TestGoogleBackend:
    GOOGLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>Best free LLM APIs of 2026</title>
          <link>https://techblog.example.com/free-llm-apis</link>
          <pubDate>Thu, 29 Oct 2026 10:00:00 GMT</pubDate>
          <description><![CDATA[<a href="https://techblog.example.com">TechBlog</a> List of free providers]]></description>
          <source url="https://techblog.example.com">TechBlog</source>
        </item>
        <item>
          <title>New AI startup offers free tier</title>
          <link>https://news.example.org/startup</link>
          <pubDate>Thu, 29 Oct 2026 09:00:00 GMT</pubDate>
          <description><![CDATA[<a href="https://news.example.org">News</a> Free tier details]]></description>
          <source url="https://news.example.org">News</source>
        </item>
      </channel>
    </rss>"""

    @pytest.fixture(autouse=True)
    def _clean_google_env(self, monkeypatch):
        """Xoá env Google cho mỗi test — trạng thái fallback mặc định là RSS."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_CSE_ID", raising=False)
        from src.config import get_google_config

        get_google_config.cache_clear()
        yield
        get_google_config.cache_clear()

    def test_fallback_news_rss_when_no_key(self, monkeypatch):
        from src.discovery.websearch.backends import search_google

        captured_urls = []

        def fake_get(url, **kw):
            captured_urls.append(url)

            class Resp:
                status_code = 200
                text = self.GOOGLE_RSS
                headers = {"content-type": "application/xml"}

                def json(self):
                    return {}

                def raise_for_status(self):
                    pass

            return Resp()

        monkeypatch.setattr("httpx.get", fake_get)
        results = search_google("free llm api", max_results=10, timeout=1.0)
        assert len(results) == 2
        assert all(r.source == "google" for r in results)
        assert results[0].url == "https://techblog.example.com/free-llm-apis"
        assert "TechBlog" in results[0].snippet  # news source được ghép vào snippet
        assert "<a " not in results[0].snippet  # HTML đã được làm sạch
        assert "news.google.com/rss/search" in captured_urls[0]  # dùng RSS, không dùng CSE

    def test_custom_search_used_when_configured(self, monkeypatch):
        from src.discovery.websearch.backends import search_google

        captured_urls = []

        def fake_get(url, **kw):
            captured_urls.append(url)

            class Resp:
                status_code = 200
                text = ""
                headers = {"content-type": "application/json"}

                def json(self):
                    return {
                        "items": [
                            {
                                "title": "Free LLM API list",
                                "link": "https://provider.example.com/free",
                                "snippet": "Get a free API key",
                                "displayLink": "provider.example.com",
                            }
                        ]
                    }

                def raise_for_status(self):
                    pass

            return Resp()

        monkeypatch.setattr("httpx.get", fake_get)
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_CSE_ID", "test-cx")
        from src.config import get_google_config

        get_google_config.cache_clear()
        results = search_google("free llm api", max_results=10, timeout=1.0)
        assert len(results) == 1
        assert results[0].url == "https://provider.example.com/free"
        assert results[0].source == "google"
        assert "customsearch/v1" in captured_urls[0]  # đúng endpoint CSE
        assert "key=test-key" in captured_urls[0] and "cx=test-cx" in captured_urls[0]

    def test_cse_error_falls_back_to_rss(self, monkeypatch):
        """CSE lỗi (network/schema) → tự chuyển sang Google News RSS, không crash."""
        from src.discovery.websearch.backends import search_google

        def fake_get(url, **kw):
            if "customsearch" in url:
                raise httpx.ConnectError("down")
            assert "news.google.com/rss/search" in url

            class Resp:
                status_code = 200
                text = self.GOOGLE_RSS
                headers = {"content-type": "application/xml"}

                def json(self):
                    return {}

                def raise_for_status(self):
                    pass

            return Resp()

        monkeypatch.setattr("httpx.get", fake_get)
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_CSE_ID", "test-cx")
        from src.config import get_google_config

        get_google_config.cache_clear()
        results = search_google("free llm api", timeout=1.0)
        assert len(results) == 2  # RSS fallback vẫn trả kết quả

    def test_cse_empty_items_falls_back_to_rss(self, monkeypatch):
        from src.discovery.websearch.backends import search_google

        def fake_get(url, **kw):
            if "customsearch" in url:

                class Resp:
                    status_code = 200
                    text = ""
                    headers = {"content-type": "application/json"}

                    def json(self):
                        return {"items": []}

                    def raise_for_status(self):
                        pass

                return Resp()

            class RSSResp:
                status_code = 200
                text = self.GOOGLE_RSS
                headers = {"content-type": "application/xml"}

                def json(self):
                    return {}

                def raise_for_status(self):
                    pass

            return RSSResp()

        monkeypatch.setattr("httpx.get", fake_get)
        monkeypatch.setenv("GOOGLE_API_KEY", "k")
        monkeypatch.setenv("GOOGLE_CSE_ID", "cx")
        from src.config import get_google_config

        get_google_config.cache_clear()
        results = search_google("q", timeout=1.0)
        assert len(results) == 2

    def test_malformed_rss_raises(self, monkeypatch):
        from src.discovery.websearch.backends import search_google

        def fake_get(url, **kw):
            class Resp:
                status_code = 200
                text = "<rss><channel><item>không đóng thẻ"
                headers = {"content-type": "application/xml"}

                def json(self):
                    return {}

                def raise_for_status(self):
                    pass

            return Resp()

        monkeypatch.setattr("httpx.get", fake_get)
        with pytest.raises(RuntimeError, match="RSS"):
            search_google("q", timeout=1.0)

    def test_registered_in_backends(self):
        from src.discovery.websearch.backends import SEARCH_BACKENDS

        assert "google" in SEARCH_BACKENDS
        assert "google" in AVAILABLE_SOURCES

    def test_google_config_is_configured(self):
        from src.config import GoogleSearchConfig

        assert GoogleSearchConfig(GOOGLE_API_KEY="", GOOGLE_CSE_ID="").is_configured() is False
        assert GoogleSearchConfig(GOOGLE_API_KEY="k", GOOGLE_CSE_ID="").is_configured() is False
        assert GoogleSearchConfig(GOOGLE_API_KEY="k", GOOGLE_CSE_ID="cx").is_configured() is True


# ---------------------------------------------------------------------------
# ScanState — trạng thái quét giữa các lần chạy
# ---------------------------------------------------------------------------


class TestScanState:
    def test_roundtrip(self, tmp_path):
        from src.storage.scan_state import ScanState

        path = tmp_path / "state.json"
        state = ScanState(path)
        state.mark_seen_urls(["https://a.com/1", "https://a.com/1"])
        state.used_keywords.update(["Free LLM api"])
        state.merge_providers([Provider(name="P1", base_url="https://api.p1.ai/v1")])
        state.save()

        loaded = ScanState.load(path)
        assert loaded.seen_urls == {"https://a.com/1"}
        assert loaded.used_keywords == {"free llm api"}
        assert [p.name for p in loaded.providers] == ["P1"]

    def test_load_missing_file_returns_empty(self, tmp_path):
        from src.storage.scan_state import ScanState

        state = ScanState.load(tmp_path / "nope.json")
        assert state.seen_urls == set()
        assert state.providers == []

    def test_load_corrupted_file_resets(self, tmp_path):
        from src.storage.scan_state import ScanState

        path = tmp_path / "state.json"
        path.write_text("{broken", encoding="utf-8")
        state = ScanState.load(path)
        assert state.seen_urls == set()
        assert state.providers == []

    def test_filter_new_urls(self, tmp_path):
        from src.discovery.websearch.backends import SearchResult
        from src.storage.scan_state import ScanState

        state = ScanState(tmp_path / "state.json")
        state.mark_seen_urls(["https://old.com/a"])
        items = [
            SearchResult(title="old", url="https://old.com/A"),  # trùng (case-insensitive)
            SearchResult(title="new", url="https://new.com/b"),
        ]
        fresh = state.filter_new_urls(items)
        assert [r.url for r in fresh] == ["https://new.com/b"]

    def test_merge_providers_dedupes(self, tmp_path):
        from src.storage.scan_state import ScanState

        state = ScanState(tmp_path / "state.json")
        first = [Provider(name="P1", base_url="https://api.p1.ai/v1")]
        assert len(state.merge_providers(first)) == 1
        # Trùng URL → không thêm
        assert (
            len(state.merge_providers([Provider(name="X", base_url="https://API.P1.AI/v1")])) == 0
        )
        # Trùng tên → không thêm
        assert (
            len(state.merge_providers([Provider(name="p1", base_url="https://other.ai/v1")])) == 0
        )
        # Mới → thêm
        assert (
            len(state.merge_providers([Provider(name="P2", base_url="https://api.p2.ai/v1")])) == 1
        )
        assert len(state.providers) == 2

    def test_pick_fresh_keywords_rotation_and_batch(self, tmp_path):
        from src.storage.scan_state import ScanState

        state = ScanState(tmp_path / "state.json")
        pool = [f"kw-{i}" for i in range(20)]
        batch1 = state.pick_fresh_keywords(pool, [])
        assert batch1 == pool[:8]
        state.used_keywords.update(batch1)
        batch2 = state.pick_fresh_keywords(pool, [])
        assert batch2 == pool[8:16]
        assert set(batch1).isdisjoint(batch2)

    def test_pick_fresh_keywords_cycle_restart(self, tmp_path):
        from src.storage.scan_state import ScanState

        state = ScanState(tmp_path / "state.json")
        pool = ["a", "b"]
        state.used_keywords.update(pool)
        # Pool cạn → bắt đầu chu kỳ mới từ đầu pool
        assert state.pick_fresh_keywords(pool, []) == ["a", "b"]

    def test_pick_fresh_keywords_user_override(self, tmp_path):
        from src.storage.scan_state import ScanState

        state = ScanState(tmp_path / "state.json")
        assert state.pick_fresh_keywords(["pool-1"], ["user kw"]) == ["user kw"]

    def test_context_manager_saves_on_exception(self, tmp_path):
        from src.storage.scan_state import ScanState

        path = tmp_path / "state.json"
        with pytest.raises(RuntimeError):
            with ScanState(path) as state:
                state.mark_seen_urls(["https://x.com/1"])
                raise RuntimeError("crash giữa chừng")
        # Dù crash, trạng thái vẫn được lưu
        assert ScanState.load(path).seen_urls == {"https://x.com/1"}

    def test_merge_providers_updates_existing_info(self, tmp_path):
        """Provider tìm lại phải được CẬP NHẬT info (model mới) — không bị bỏ qua."""
        from src.storage.scan_state import ScanState

        state = ScanState(tmp_path / "state.json")
        old = Provider(name="P1", base_url="https://api.p1.ai/v1", models=[])
        state.merge_providers([old])
        assert state.last_merge_updated == []

        # Tìm lại cùng provider, lần này AI trích xuất được model thật
        refreshed = Provider(
            name="P1",
            base_url="https://api.p1.ai/v1",
            models=[{"id": "free-m", "name": "Free M", "is_free": True}],
            description="free tier 2026",
        )
        added = state.merge_providers([refreshed])
        assert added == []  # không thêm trùng
        assert len(state.last_merge_updated) == 1
        saved = state.providers[0]
        assert [m.id for m in saved.models] == ["free-m"]  # model được cập nhật
        assert "free tier 2026" in saved.description

    def test_merge_providers_no_update_flag(self, tmp_path):
        """update_existing=False → bỏ qua provider trùng như hành vi cũ."""
        from src.storage.scan_state import ScanState

        state = ScanState(tmp_path / "state.json")
        state.merge_providers([Provider(name="P1", base_url="https://api.p1.ai/v1")])
        again = Provider(
            name="P1",
            base_url="https://api.p1.ai/v1",
            models=[{"id": "m2", "name": "M2"}],
        )
        assert state.merge_providers([again], update_existing=False) == []
        assert state.last_merge_updated == []
        assert state.providers[0].models == []

    def test_run_history_recorded_and_persisted(self, tmp_path):
        """record_run lưu timestamp + keyword; roundtrip qua file giữ nguyên."""
        from src.storage.scan_state import ScanState

        path = tmp_path / "state.json"
        state = ScanState(path)
        state.record_run(["kw-a", "kw-b"], added=2, updated=1, mode="ai")
        state.save()

        loaded = ScanState.load(path)
        assert len(loaded.run_history) == 1
        entry = loaded.run_history[0]
        assert entry["keywords"] == ["kw-a", "kw-b"]
        assert entry["new_providers"] == 2
        assert entry["updated_providers"] == 1
        assert entry["mode"] == "ai"
        assert "run_at" in entry  # timestamp phân biệt các lần scan

    def test_load_v1_state_without_run_history(self, tmp_path):
        """File state cũ (v1, không run_history) phải load được — backward compatible."""
        from src.storage.scan_state import ScanState

        path = tmp_path / "state.json"
        legacy = {
            "version": 1,
            "seen_urls": ["https://old.com/a"],
            "used_keywords": ["kw-old"],
            "providers": [],
        }
        path.write_text(json.dumps(legacy), encoding="utf-8")
        loaded = ScanState.load(path)
        assert loaded.seen_urls == {"https://old.com/a"}
        assert loaded.run_history == []  # thiếu → mặc định rỗng, không crash
