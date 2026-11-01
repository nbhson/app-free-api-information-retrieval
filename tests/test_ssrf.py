"""Tests cho src.verification.ssrf (SSRF guard) + tích hợp với checker — mock DNS, không network."""

import httpx
import pytest

from src.models import ProviderStatus
from src.verification import checker, ssrf
from src.verification.checker import verify_provider
from src.verification.ssrf import SSRFBlockedError, is_private_ip, validate_url

# Giữ tham chiếu class gốc TRƯỚC khi monkeypatch (tránh đệ quy — như test_checker)
_RealAsyncClient = httpx.AsyncClient


class TestIsPrivateIp:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",
            "10.0.0.5",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.1.1",
            "169.254.169.254",  # cloud metadata endpoint
            "100.64.0.1",  # CGNAT
            "0.0.0.0",
            "::1",
            "fc00::1",
            "fe80::1",
            "::ffff:127.0.0.1",  # IPv4-mapped IPv6
            "::ffff:10.0.0.1",
        ],
    )
    def test_private_blocked(self, ip):
        assert is_private_ip(ip) is True

    @pytest.mark.parametrize(
        "ip",
        ["8.8.8.8", "93.184.216.34", "172.32.0.1", "2606:4700::1111"],
    )
    def test_public_allowed(self, ip):
        assert is_private_ip(ip) is False

    def test_invalid_ip_not_private(self):
        assert is_private_ip("not-an-ip") is False


class TestValidateUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://api.example.com/v1/models",
            "http://api.example.com/v1/models",
            "https://openrouter.ai/api/v1",
        ],
    )
    def test_public_urls_pass(self, url):
        assert validate_url(url) == url

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://example.com/file",
            "gopher://example.com",
        ],
    )
    def test_non_http_scheme_blocked(self, url):
        with pytest.raises(SSRFBlockedError, match="scheme"):
            validate_url(url)

    def test_missing_hostname_blocked(self):
        with pytest.raises(SSRFBlockedError, match="hostname"):
            validate_url("https:///path")

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:8000/api",
            "http://sub.localhost/api",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://instance-data/latest",
        ],
    )
    def test_blocked_hostnames(self, url):
        with pytest.raises(SSRFBlockedError):
            validate_url(url)

    def test_lookalike_public_hostname_allowed(self):
        """localhost.evil.com là domain public hợp lệ — KHÔNG bị chặn."""
        assert validate_url("http://localhost.evil.com/api")

    def test_userinfo_blocked(self):
        with pytest.raises(SSRFBlockedError, match="credentials"):
            validate_url("http://user:pass@api.example.com/v1")

    def test_direct_private_ip_blocked(self):
        with pytest.raises(SSRFBlockedError, match="private"):
            validate_url("http://127.0.0.1:8000/api/v1")

    def test_metadata_ip_blocked(self):
        with pytest.raises(SSRFBlockedError, match="private"):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_hostname_resolving_to_private_ip_blocked(self, monkeypatch):
        """Hostname trỏ 127.0.0.1 → chặn (fake DNS, không cần network)."""
        monkeypatch.setattr(ssrf, "resolve_hostname", lambda host: ["127.0.0.1"])
        with pytest.raises(SSRFBlockedError, match="127.0.0.1"):
            validate_url("http://internal-service.example.com/v1/models")

    def test_hostname_resolving_to_metadata_ip_blocked(self, monkeypatch):
        monkeypatch.setattr(
            ssrf, "resolve_hostname", lambda host: ["93.184.216.34", "169.254.169.254"]
        )
        with pytest.raises(SSRFBlockedError, match="169.254.169.254"):
            validate_url("http://rebind.example.com/v1/models")

    def test_dns_failure_blocked(self, monkeypatch):
        def boom(host):
            raise OSError("nodename nor servname provided")

        monkeypatch.setattr(ssrf, "resolve_hostname", boom)
        with pytest.raises(SSRFBlockedError, match="DNS lookup"):
            validate_url("https://nonexistent.invalid/v1/models")


# ─── Tích hợp với checker.verify_provider ───


def _client_with(handler):
    """Client dùng MockTransport — gọi class gốc, không phải bản đã patch."""
    return _RealAsyncClient(transport=httpx.MockTransport(handler))


class TestVerifyProviderSsrfGuard:
    async def test_private_base_url_blocked_before_request(self, sample_provider):
        """base_url là IP private → chặn trước khi gửi request (không fetch nào)."""
        sample_provider.base_url = "http://127.0.0.1:11434/v1"
        sent = []

        def handler(request):
            sent.append(str(request.url))
            return httpx.Response(200, json={"data": []})

        def fake_client(**kw):
            kw["transport"] = httpx.MockTransport(handler)
            return _RealAsyncClient(**kw)

        import unittest.mock as _m

        with _m.patch.object(checker.httpx, "AsyncClient", side_effect=fake_client):
            result = await verify_provider(sample_provider)

        assert sent == []  # không request nào ra khỏi guard
        assert result.status == ProviderStatus.UNKNOWN

    async def test_hostname_resolving_private_blocked(self, sample_provider, monkeypatch):
        """DNS fake: hostname resolve về 127.0.0.1 → chặn (không cần network)."""
        monkeypatch.setattr(ssrf, "resolve_hostname", lambda host: ["127.0.0.1"])
        result = await verify_provider(sample_provider)
        assert result.status == ProviderStatus.UNKNOWN

    async def test_public_url_still_works(self, sample_provider, monkeypatch):
        """Happy path: URL public vẫn verify bình thường qua guard."""

        def handler(request):
            return httpx.Response(200, json={"data": [{"id": "m1", "name": "m1"}]})

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _client_with(handler))
        result = await verify_provider(sample_provider)
        assert result.status == ProviderStatus.ACTIVE

    async def test_redirect_followed_within_limit(self, sample_provider, monkeypatch):
        """Redirect hợp lệ (public → public) được follow và verify ACTIVE."""
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(302, headers={"Location": "https://api.example.com/v1/models"})
            return httpx.Response(200, json={"data": []})

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _client_with(handler))
        result = await verify_provider(sample_provider)
        assert result.status == ProviderStatus.ACTIVE
        assert calls["n"] == 2

    async def test_redirect_to_private_ip_blocked(self, sample_provider, monkeypatch):
        """Redirect trỏ về IP private/metadata → chặn ở hop 2."""
        seen_urls = []

        def handler(request):
            seen_urls.append(str(request.url))
            return httpx.Response(
                302, headers={"Location": "http://169.254.169.254/latest/meta-data/"}
            )

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _client_with(handler))
        result = await verify_provider(sample_provider)
        assert result.status == ProviderStatus.UNKNOWN
        assert len(seen_urls) == 1  # chỉ hop 1 được gửi, hop 2 bị guard chặn

    async def test_too_many_redirects_blocked(self, sample_provider, monkeypatch):
        """Redirect loop vượt MAX_REDIRECTS (3) → chặn, không request thừa."""
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(302, headers={"Location": "https://api.example.com/v1/models"})

        monkeypatch.setattr(checker.httpx, "AsyncClient", lambda **kw: _client_with(handler))
        result = await verify_provider(sample_provider)
        assert result.status == ProviderStatus.UNKNOWN
        # 1 hop gốc + 3 redirect = 4 request, không hơn
        assert calls["n"] == checker.MAX_REDIRECTS + 1
