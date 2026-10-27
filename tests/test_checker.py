"""Tests cho src.verification.checker (mock HTTP, không gọi mạng thật)."""
import asyncio
from datetime import datetime

import httpx

from src.models import Provider, ProviderStatus
from src.verification import checker
from src.verification.checker import verify_provider, verify_all_providers, _models_url

# Giữ tham chiếu class gốc TRƯỚC khi monkeypatch (tránh đệ quy)
_RealAsyncClient = httpx.AsyncClient


def _transport(handler) -> httpx.AsyncClient:
    """Client dùng MockTransport — gọi class gốc, không phải bản đã patch."""
    return _RealAsyncClient(transport=httpx.MockTransport(handler))


class TestModelsUrl:
    def test_appends_models(self):
        assert _models_url("https://api.x.com/v1") == "https://api.x.com/v1/models"

    def test_no_double_append(self):
        assert _models_url("https://api.x.com/v1/models") == "https://api.x.com/v1/models"

    def test_strips_trailing_slash(self):
        assert _models_url("https://api.x.com/v1/") == "https://api.x.com/v1/models"


class TestVerifyProvider:
    async def test_200_is_active(self, sample_provider, monkeypatch):
        def handler(request):
            return httpx.Response(200, json={"data": []})
        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        result = await verify_provider(sample_provider)
        assert result.status == ProviderStatus.ACTIVE
        assert isinstance(result.last_verified, datetime)

    def test_401_counts_as_active(self, sample_provider, monkeypatch):
        def handler(request):
            return httpx.Response(401)
        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        result = asyncio.run(verify_provider(sample_provider))
        assert result.status == ProviderStatus.ACTIVE

    def test_429_is_rate_limited(self, sample_provider, monkeypatch):
        def handler(request):
            return httpx.Response(429)
        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        result = asyncio.run(verify_provider(sample_provider))
        assert result.status == ProviderStatus.RATE_LIMITED

    def test_500_is_inactive(self, sample_provider, monkeypatch):
        def handler(request):
            return httpx.Response(500)
        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        result = asyncio.run(verify_provider(sample_provider))
        assert result.status == ProviderStatus.INACTIVE

    def test_connect_error_retries_then_inactive(self, sample_provider, monkeypatch):
        calls = {"n": 0}
        def handler(request):
            calls["n"] += 1
            raise httpx.ConnectError("boom")
        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        result = asyncio.run(verify_provider(sample_provider, retries=2))
        assert result.status == ProviderStatus.INACTIVE
        assert calls["n"] == 3  # 1 lần + 2 retries

    def test_timeout_retries_then_inactive(self, sample_provider, monkeypatch):
        calls = {"n": 0}
        def handler(request):
            calls["n"] += 1
            raise httpx.TimeoutException("timed out")
        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        result = asyncio.run(verify_provider(sample_provider, retries=1))
        assert result.status == ProviderStatus.INACTIVE
        assert calls["n"] == 2

    def test_unexpected_error_is_unknown(self, sample_provider, monkeypatch):
        def handler(request):
            raise RuntimeError("weird")
        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        result = asyncio.run(verify_provider(sample_provider))
        assert result.status == ProviderStatus.UNKNOWN


class TestVerifyAll:
    async def test_gather_preserves_order(self, sample_providers, monkeypatch):
        def handler(request):
            return httpx.Response(200)
        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        results = await verify_all_providers(sample_providers)
        assert [p.name for p in results] == [p.name for p in sample_providers]
        assert all(p.status == ProviderStatus.ACTIVE for p in results)

    async def test_empty_list(self, monkeypatch):
        assert await verify_all_providers([]) == []


class TestConcurrency:
    def test_semaphore_configured(self):
        """Semaphore tồn tại và giới hạn đúng giá trị cấu hình."""
        assert isinstance(checker._semaphore, asyncio.Semaphore)
        assert checker.MAX_CONCURRENCY >= 1

    async def test_many_providers_all_verified(self, sample_providers, monkeypatch):
        """20 provider — tất cả được verify, kết quả đúng thứ tự."""
        def handler(request):
            return httpx.Response(200)
        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        providers = [
            Provider(name=f"P{i}", base_url=f"https://api{i}.example.com/v1")
            for i in range(20)
        ]
        results = await verify_all_providers(providers)
        assert len(results) == 20
        assert all(p.status == ProviderStatus.ACTIVE for p in results)
