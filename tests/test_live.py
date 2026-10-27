"""Tests cho src.discover.live (mock HTTP)."""

import httpx
import pytest

from src.discovery.live import (
    LIVE_HEADERS,
    LiveDiscoveryError,
    _is_free,
    _parse_free_models,
    fetch_openrouter_free_models,
)


class TestIsFree:
    def test_free_when_both_zero(self):
        assert _is_free({"prompt": "0", "completion": "0"}) is True

    def test_not_free_when_completion_paid(self):
        assert _is_free({"prompt": "0", "completion": "0.0001"}) is False

    def test_paid_when_both_nonzero(self):
        assert _is_free({"prompt": "0.0001", "completion": "0.0001"}) is False
        assert _is_free({}) is False
        assert _is_free({"prompt": None, "completion": "0"}) is False

    def test_missing_pricing_is_not_free(self):
        assert _is_free({}) is False
        assert _is_free({"prompt": None}) is False


class TestParseFreeModels:
    def test_parses_only_free_models(self):
        data = {
            "data": [
                {
                    "id": "free-m",
                    "name": "Free Model",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "context_length": 4096,
                    "description": "A free model",
                },
                {
                    "id": "paid-m",
                    "name": "Paid Model",
                    "pricing": {"prompt": "0.01", "completion": "0.01"},
                },
            ]
        }
        models = _parse_free_models(data)
        assert len(models) == 1
        assert models[0].id == "free-m"
        assert models[0].is_free is True
        assert models[0].context_length == 4096
        assert models[0].supports_streaming is True
        assert models[0].description == "A free model"

    def test_empty_data_returns_empty(self):
        assert _parse_free_models({}) == []
        assert _parse_free_models({"data": []}) == []

    def test_missing_data_key(self):
        assert _parse_free_models({}) == []
        assert _parse_free_models({"foo": []}) == []


class TestFetchOpenRouterFreeModels:
    def test_base_url_param_is_used(self, monkeypatch):
        """Regression: base_url param phải được dùng thực sự, không phải hardcode."""

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"data": []}

            def raise_for_status(self):
                pass

        captured_urls = []

        def fake_get(url, **kw):
            captured_urls.append(url)
            return FakeResponse()

        monkeypatch.setattr("httpx.get", fake_get)
        fetch_openrouter_free_models(base_url="https://custom.api/v1/models", timeout=1.0)
        assert captured_urls == ["https://custom.api/v1/models"]

    def test_timeout_raises_live_discovery_error(self, monkeypatch):
        import httpx

        def fake_get(url, **kw):
            raise httpx.TimeoutException("t")

        monkeypatch.setattr("httpx.get", fake_get)
        with pytest.raises(LiveDiscoveryError, match="Timeout"):
            fetch_openrouter_free_models(timeout=1.0)

    def test_http_error_raises(self, monkeypatch):
        import httpx

        def fake_get(url, **kw):
            resp = httpx.Response(500, request=httpx.Request("GET", url))
            raise httpx.HTTPStatusError("err", request=resp.request, response=resp)

        monkeypatch.setattr("httpx.get", fake_get)
        with pytest.raises(LiveDiscoveryError, match="HTTP"):
            fetch_openrouter_free_models(timeout=1.0)

    def test_bad_json_raises(self, monkeypatch):

        class FakeResponse:
            status_code = 200

            def json(self):
                raise ValueError("bad json")

            def raise_for_status(self):
                pass

        monkeypatch.setattr("httpx.get", lambda url, **kw: FakeResponse())
        with pytest.raises(LiveDiscoveryError, match="Lỗi khi gọi"):
            fetch_openrouter_free_models(timeout=1.0)

    def test_wrong_schema_raises(self, monkeypatch):

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"wrong_key": []}

            def raise_for_status(self):
                pass

        monkeypatch.setattr("httpx.get", lambda url, **kw: FakeResponse())
        models = fetch_openrouter_free_models(timeout=1.0)
        assert models == []  # wrong schema → empty, no error (graceful)

    def test_fetch_returns_free_models(self, monkeypatch):

        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "data": [
                        {
                            "id": "free-model",
                            "name": "Free Model",
                            "pricing": {"prompt": "0", "completion": "0"},
                            "context_length": 8192,
                        }
                    ]
                }

            def raise_for_status(self):
                pass

        monkeypatch.setattr("httpx.get", lambda url, **kw: FakeResponse())
        models = fetch_openrouter_free_models(timeout=1.0)
        assert len(models) == 1
        assert models[0].id == "free-model"


class TestLiveHeaders:
    def test_user_agent_version(self):
        """User-Agent header phải chứa version hiện tại của app."""
        from src.__version__ import __version__

        assert __version__ in LIVE_HEADERS["User-Agent"]


class TestBuildOpenRouterLiveProvider:
    def test_provider_built_with_live_models(self):
        from src.discovery.live import build_openrouter_live_provider
        from src.models import Model

        models = [Model(id="m1", name="Model 1", is_free=True)]
        p = build_openrouter_live_provider(models)
        assert p.name == "OpenRouter"
        assert p.status.value == "active"

    def test_provider_models_all_free(self):
        from src.discovery.live import build_openrouter_live_provider
        from src.models import Model

        models = [Model(id="m1", name="M1", is_free=True)]
        p = build_openrouter_live_provider(models)
        assert all(m.is_free for m in p.models)

    def test_provider_tagged_live_discovered(self):
        from src.discovery.live import build_openrouter_live_provider
        from src.models import Model

        models = [Model(id="m1", name="M1", is_free=True)]
        p = build_openrouter_live_provider(models)
        assert "live-discovered" in p.tags


class TestDiscoverLive:
    def test_discover_live_success(self, monkeypatch):
        from src.discovery.live import discover_live

        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "data": [
                        {
                            "id": "m1",
                            "name": "Model 1",
                            "pricing": {"prompt": "0", "completion": "0"},
                        }
                    ]
                }

            def raise_for_status(self):
                pass

        monkeypatch.setattr("httpx.get", lambda url, **kw: FakeResponse())
        p = discover_live()
        assert p.name == "OpenRouter"
        assert len(p.get_free_models()) == 1

    def test_discover_live_no_free_models_raises(self, monkeypatch):
        from src.discovery.live import discover_live

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"data": []}

            def raise_for_status(self):
                pass

        monkeypatch.setattr("httpx.get", lambda url, **kw: FakeResponse())
        with pytest.raises(LiveDiscoveryError, match="không trả về model free"):
            discover_live()


class TestFetchRetry:
    """Retry logic của live discovery (plan item N4)."""

    def test_retries_on_503_then_raises(self, monkeypatch):
        calls_count = {"n": 0}

        class ErrorResponse:
            status_code = 503

            def raise_for_status(self):
                resp = httpx.Response(503, request=httpx.Request("GET", "https://x.com"))
                raise httpx.HTTPStatusError("err", request=resp.request, response=resp)

        def fake_get(url, **kw):
            calls_count["n"] += 1
            return ErrorResponse()

        monkeypatch.setattr("httpx.get", fake_get)
        monkeypatch.setattr("src.discovery.live.time.sleep", lambda s: None)
        with pytest.raises(LiveDiscoveryError, match="503"):
            fetch_openrouter_free_models(timeout=1.0, retries=1)
        assert calls_count["n"] == 2  # 1 lần + 1 retry

    def test_recovers_on_503(self, monkeypatch):
        """503 lần đầu, 200 lần sau → trả về models (retry có tác dụng)."""
        calls_count = {"n": 0}

        class OkResponse:
            status_code = 200

            def json(self):
                return {
                    "data": [
                        {"id": "m1", "name": "M1", "pricing": {"prompt": "0", "completion": "0"}}
                    ]
                }

            def raise_for_status(self):
                pass

        class ErrorResponse:
            status_code = 503

            def raise_for_status(self):
                resp = httpx.Response(503, request=httpx.Request("GET", "https://x.com"))
                raise httpx.HTTPStatusError("err", request=resp.request, response=resp)

        def fake_get(url, **kw):
            calls_count["n"] += 1
            if calls_count["n"] == 1:
                return ErrorResponse()
            return OkResponse()

        monkeypatch.setattr("httpx.get", fake_get)
        monkeypatch.setattr("src.discovery.live.time.sleep", lambda s: None)
        models = fetch_openrouter_free_models(timeout=1.0)
        assert len(models) == 1

    def test_502_raises_immediately_when_not_retryable(self, monkeypatch):
        """404 (không thuộc retryable) → raise ngay, không retry."""
        calls_count = {"n": 0}

        class ErrorResponse:
            status_code = 404

            def raise_for_status(self):
                resp = httpx.Response(404, request=httpx.Request("GET", "https://x.com"))
                raise httpx.HTTPStatusError("err", request=resp.request, response=resp)

        def fake_get(url, **kw):
            calls_count["n"] += 1
            return ErrorResponse()

        monkeypatch.setattr("httpx.get", fake_get)
        with pytest.raises(LiveDiscoveryError, match="404"):
            fetch_openrouter_free_models(timeout=1.0, retries=2)
        assert calls_count["n"] == 1  # không retry
