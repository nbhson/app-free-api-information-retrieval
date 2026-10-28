"""Tests cho src.verification.checker (mock HTTP, không gọi mạng thật)."""

import asyncio
from datetime import datetime

import httpx

from src.models import Provider, ProviderStatus
from src.verification import checker
from src.verification.checker import _models_url, verify_all_providers, verify_provider

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

    def test_429_retries_then_rate_limited(self, sample_provider, monkeypatch):
        """429 phải được retry trước khi trả về RATE_LIMITED."""
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(429)

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        result = asyncio.run(verify_provider(sample_provider, retries=1))
        assert calls["n"] == 2
        assert result.status == ProviderStatus.RATE_LIMITED

    def test_429_recovers_on_retry(self, sample_provider, monkeypatch):
        """429 ở lần đầu, 200 ở lần sau → ACTIVE (retry có tác dụng)."""
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429)
            return httpx.Response(200)

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        result = asyncio.run(verify_provider(sample_provider))
        assert result.status == ProviderStatus.ACTIVE
        assert calls["n"] == 2

    def test_500_retries_then_inactive(self, sample_provider, monkeypatch):
        """HTTP 5xx là lỗi tạm thời — retry hết lượt rồi mới INACTIVE."""
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(500)

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        result = asyncio.run(verify_provider(sample_provider, retries=2))
        assert calls["n"] == 3  # 1 lần + 2 retries
        assert result.status == ProviderStatus.INACTIVE

    def test_503_retries_then_inactive(self, sample_provider, monkeypatch):
        """HTTP 503 là lỗi tạm thời — phải retry hết lượt rồi mới INACTIVE."""
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(503)

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        result = asyncio.run(verify_provider(sample_provider, retries=2))
        assert calls["n"] == 3  # 1 lần + 2 retries
        assert result.status == ProviderStatus.INACTIVE

    def test_503_recovers_on_retry(self, sample_provider, monkeypatch):
        """503 ở lần đầu, 200 ở lần sau → ACTIVE."""
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(503)
            return httpx.Response(200)

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        result = asyncio.run(verify_provider(sample_provider))
        assert result.status == ProviderStatus.ACTIVE
        assert calls["n"] == 2

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


class TestProgressCallback:
    async def test_callback_called_per_provider(self, sample_providers, monkeypatch):
        def handler(request):
            return httpx.Response(200)

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        calls: list[tuple[int, int, str]] = []
        results = await verify_all_providers(
            sample_providers,
            progress_callback=lambda done, total, p: calls.append((done, total, p.name)),
        )
        assert len(calls) == len(sample_providers)
        # completed tăng dần 1..n
        assert [c[0] for c in calls] == list(range(1, len(sample_providers) + 1))
        # total đúng bằng số provider
        assert all(c[1] == len(sample_providers) for c in calls)
        # callback nhận đúng provider vừa verify (status đã cập nhật)
        assert all(c[2] in {p.name for p in results} for c in calls)

    async def test_no_callback_is_default(self, sample_providers, monkeypatch):
        """Không truyền callback → vẫn hoạt động bình thường (backward compatible)."""

        def handler(request):
            return httpx.Response(200)

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        results = await verify_all_providers(sample_providers)
        assert len(results) == 2


class TestConcurrency:
    def test_max_concurrency_configured(self):
        """Giá trị cấu hình concurrency hợp lệ."""
        assert checker.MAX_CONCURRENCY >= 1

    def test_verify_provider_does_not_mutate_original(self, sample_provider, monkeypatch):
        """verify_provider trả về bản copy — không mutate provider gốc trong registry."""

        def handler(request):
            return httpx.Response(200)

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        original_status = sample_provider.status
        result = asyncio.run(verify_provider(sample_provider))
        assert result is not sample_provider
        assert result.status == ProviderStatus.ACTIVE
        assert sample_provider.status == original_status
        assert sample_provider.last_verified is None

    async def test_verify_all_does_not_mutate_originals(self, sample_providers, monkeypatch):
        """verify_all_providers không mutate các provider đầu vào."""
        statuses_before = [p.status for p in sample_providers]

        def handler(request):
            return httpx.Response(200)

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        results = await verify_all_providers(sample_providers)
        assert all(r is not p for r, p in zip(results, sample_providers, strict=False))
        assert [p.status for p in sample_providers] == statuses_before
        assert all(p.status == ProviderStatus.ACTIVE for p in results)

    async def test_many_providers_all_verified(self, sample_providers, monkeypatch):
        """20 provider — tất cả được verify, kết quả đúng thứ tự."""

        def handler(request):
            return httpx.Response(200)

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _transport(handler))
        providers = [
            Provider(name=f"P{i}", base_url=f"https://api{i}.example.com/v1") for i in range(20)
        ]
        results = await verify_all_providers(providers)
        assert len(results) == 20
        assert all(p.status == ProviderStatus.ACTIVE for p in results)
