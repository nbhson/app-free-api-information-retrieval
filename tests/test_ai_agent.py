"""Tests cho src.discovery.ai_agent (mock HTTP)."""

import json

import httpx
import pytest

from src.config import AIConfig
from src.discovery import ai_agent
from src.discovery.ai_agent import (
    AIDiscoveryError,
    _extract_json,
    _parse_providers,
    discover_with_ai,
)

VALID_RESPONSE = {
    "providers": [
        {
            "name": "New Provider",
            "base_url": "https://api.new.com/v1/",
            "website": "https://new.com",
            "description": "desc",
            "api_style": "openai",
            "auth_required": "true",
            "rate_limit": "10/min",
            "tags": ["t1"],
            "free_models": [{"id": "m1", "name": "M One", "context_length": 4096}],
        }
    ]
}


def _make_config() -> AIConfig:
    return AIConfig(
        AI_PROVIDER_BASE_URL="https://ai.test.com/v1",
        AI_API_KEY="sk-test",
        AI_MODEL="test-model",
        AI_TIMEOUT=5,
    )


class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_markdown_fence(self):
        assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_json_with_surrounding_text(self):
        text = 'Here is result: {"a": {"b": 1}} hope it helps'
        assert _extract_json(text) == {"a": {"b": 1}}

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            _extract_json("no json here")

    def test_unbalanced_raises(self):
        with pytest.raises(ValueError):
            _extract_json('{"a": 1')

    def test_brace_inside_string_value(self):
        """Regression: JSON chứa { } trong string value phải parse đúng."""
        text = '{"a": "value with } brace and { another", "b": 2}'
        assert _extract_json(text) == {"a": "value with } brace and { another", "b": 2}

    def test_non_object_raises(self):
        with pytest.raises(ValueError):
            _extract_json("[1, 2, 3]")


class TestParseProviders:
    def test_valid_entry(self):
        providers = _parse_providers(VALID_RESPONSE)
        assert len(providers) == 1
        p = providers[0]
        assert p.name == "New Provider"
        assert p.base_url == "https://api.new.com/v1"
        assert "ai-discovered" in p.tags
        assert "t1" in p.tags
        assert len(p.models) == 1
        assert p.models[0].is_free is True

    def test_invalid_api_style_falls_back_to_custom(self):
        data = {"providers": [{"name": "X", "base_url": "https://x.com", "api_style": "weird"}]}
        assert _parse_providers(data)[0].api_style.value == "custom"

    def test_auth_required_string_parsing(self):
        data = {"providers": [{"name": "X", "base_url": "https://x.com", "auth_required": "no"}]}
        assert _parse_providers(data)[0].auth_required is False

    def test_empty_data(self):
        assert _parse_providers({}) == []


class TestDiscoverWithAI:
    def test_raises_when_not_configured(self):
        cfg = AIConfig(AI_PROVIDER_BASE_URL="", AI_API_KEY="", AI_MODEL="")
        with pytest.raises(AIDiscoveryError, match="Chưa cấu hình"):
            discover_with_ai(config=cfg)

    def test_raises_on_401(self, monkeypatch):
        def fake_post(url, **kw):
            return httpx.Response(401, request=httpx.Request("POST", url))

        monkeypatch.setattr(ai_agent.httpx, "post", fake_post)
        with pytest.raises(AIDiscoveryError, match="401"):
            discover_with_ai(config=_make_config())

    def test_success_returns_providers(self, monkeypatch):
        def fake_post(url, **kw):
            content = json.dumps(VALID_RESPONSE)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": content}}]},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(ai_agent.httpx, "post", fake_post)
        providers = discover_with_ai(config=_make_config())
        assert len(providers) == 1
        assert providers[0].tags == ["t1", "ai-discovered"]

    def test_retries_on_timeout(self, monkeypatch):
        calls = {"n": 0}

        def fake_post(url, **kw):
            calls["n"] += 1
            raise ai_agent.httpx.TimeoutException("t")

        monkeypatch.setattr(ai_agent.httpx, "post", fake_post)
        with pytest.raises(AIDiscoveryError, match="Timeout"):
            discover_with_ai(config=_make_config(), max_retries=2)
        assert calls["n"] == 3

    def test_retries_on_429_then_raises(self, monkeypatch):
        """HTTP 429 là lỗi tạm thời — phải retry hết lượt rồi mới raise."""
        calls = {"n": 0}

        def fake_post(url, **kw):
            calls["n"] += 1
            return httpx.Response(429, request=httpx.Request("POST", url))

        monkeypatch.setattr(ai_agent.httpx, "post", fake_post)
        with pytest.raises(AIDiscoveryError, match="429"):
            discover_with_ai(config=_make_config(), max_retries=2)
        assert calls["n"] == 3

    def test_recovers_on_429(self, monkeypatch):
        """429 ở lần đầu, thành công ở lần sau → trả về providers."""
        calls = {"n": 0}

        def fake_post(url, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, request=httpx.Request("POST", url))
            content = json.dumps(VALID_RESPONSE)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": content}}]},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(ai_agent.httpx, "post", fake_post)
        providers = discover_with_ai(config=_make_config())
        assert len(providers) == 1

    def test_retries_on_5xx(self, monkeypatch):
        """HTTP 500 là lỗi tạm thời — phải retry, không raise ngay."""
        calls = {"n": 0}

        def fake_post(url, **kw):
            calls["n"] += 1
            return httpx.Response(503, request=httpx.Request("POST", url))

        monkeypatch.setattr(ai_agent.httpx, "post", fake_post)
        with pytest.raises(AIDiscoveryError, match="503"):
            discover_with_ai(config=_make_config(), max_retries=1)
        assert calls["n"] == 2  # 1 lần + 1 retry
