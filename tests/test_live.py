"""Tests cho src.discovery.live — live discovery từ OpenRouter API (mock network)."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.discovery.live import (
    LiveDiscoveryError,
    _is_free,
    _parse_free_models,
    build_openrouter_live_provider,
    discover_live,
    fetch_openrouter_free_models,
)
from src.models import ProviderStatus


def _fake_response(payload: dict, status_code: int = 200):
    resp = httpx.Response(status_code, json=payload, request=httpx.Request("GET", "http://t"))
    return resp


FAKE_PAYLOAD = {
    "data": [
        {
            "id": "meta-llama/llama-3.1-8b-instruct:free",
            "name": "Llama 3.1 8B Instruct (free)",
            "context_length": 131072,
            "description": "Free model",
            "pricing": {"prompt": "0", "completion": "0"},
        },
        {
            "id": "openai/gpt-4o",
            "name": "GPT-4o",
            "context_length": 128000,
            "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
        },
        {
            "id": "mistralai/mistral-7b:free",
            "name": "Mistral 7B (free)",
            "context_length": 32768,
            "pricing": {"prompt": "0", "completion": "0"},
        },
        # Free prompt nhưng completion có phí → KHÔNG free
        {
            "id": "edge/case-partial",
            "name": "Partial free",
            "pricing": {"prompt": "0", "completion": "0.000001"},
        },
        # Thiếu pricing hoàn toàn → skip
        {"id": "edge/no-pricing", "name": "No pricing"},
    ]
}


class TestIsFree:
    def test_free_when_both_zero(self):
        assert _is_free({"prompt": "0", "completion": "0"}) is True

    def test_not_free_when_completion_paid(self):
        assert _is_free({"prompt": "0", "completion": "0.000001"}) is False

    def test_paid_when_both_nonzero(self):
        assert _is_free({"prompt": "0.000002", "completion": "0.00001"}) is False

    def test_missing_pricing_is_not_free(self):
        assert _is_free({}) is False


class TestParseFreeModels:
    def test_parses_only_free_models(self):
        models = _parse_free_models(FAKE_PAYLOAD)
        assert models[0].id == "meta-llama/llama-3.1-8b-instruct:free"
        assert all(m.is_free for m in models)
        assert len(models) == 2

    def test_empty_data_returns_empty(self):
        assert _parse_free_models({"data": []}) == []

    def test_missing_data_key(self):
        assert _parse_free_models({}) == []


class TestFetchOpenRouterFreeModels:
    def test_fetch_returns_free_models(self):
        fake = MagicMock(status_code=200)
        fake.raise_for_status = lambda: None
        fake.json = lambda: FAKE_PAYLOAD
        with patch("src.discovery.live.httpx.get", return_value=fake):
            models = fetch_openrouter_free_models()
        assert [m.id for m in models] == [
            "meta-llama/llama-3.1-8b-instruct:free",
            "mistralai/mistral-7b:free",
        ]

    def test_timeout_raises_live_discovery_error(self):
        with patch("src.discovery.live.httpx.get", side_effect=httpx.TimeoutException("t/o")):
            with pytest.raises(LiveDiscoveryError, match="Timeout"):
                fetch_openrouter_free_models()

    def test_http_error_raises(self):
        resp = httpx.Response(500, request=httpx.Request("GET", "https://x"))
        with patch(
            "src.discovery.live.httpx.get",
            side_effect=httpx.HTTPStatusError("boom", request=resp.request, response=resp),
        ):
            with pytest.raises(LiveDiscoveryError, match="HTTP 500"):
                fetch_openrouter_free_models()

    def test_bad_json_raises(self):
        fake = MagicMock(status_code=200)
        fake.raise_for_status = lambda: None
        fake.json = lambda: (_ for _ in ()).throw(ValueError("invalid json"))
        with patch("src.discovery.live.httpx.get", return_value=fake):
            with pytest.raises(LiveDiscoveryError):
                fetch_openrouter_free_models()

    def test_wrong_schema_raises(self):
        # data là list chuỗi thay vì dict → AttributeError được wrap thành LiveDiscoveryError
        fake = MagicMock(status_code=200)
        fake.raise_for_status = lambda: None
        fake.json = lambda: {"data": ["not-a-dict"]}
        with patch("src.discovery.live.httpx.get", return_value=fake):
            with pytest.raises(LiveDiscoveryError, match="không đúng cấu trúc"):
                fetch_openrouter_free_models()


class TestBuildOpenRouterLiveProvider:
    def test_provider_built_with_live_models(self):
        models = _parse_free_models(FAKE_PAYLOAD)
        p = build_openrouter_live_provider(models)
        assert p.name == "OpenRouter"
        assert p.status == ProviderStatus.ACTIVE
        assert len(p.models) == 2
        assert "live-discovered" in p.tags
        assert str(len(models)) in p.description

    def test_provider_models_all_free(self):
        models = _parse_free_models(FAKE_PAYLOAD)
        assert all(m.is_free for m in models)


class TestDiscoverLive:
    def test_discover_live_success(self):
        fake = MagicMock(status_code=200)
        fake.raise_for_status = lambda: None
        fake.json = lambda: FAKE_PAYLOAD
        with patch("src.discovery.live.httpx.get", return_value=fake):
            p = discover_live()
        assert p.name == "OpenRouter"
        assert len(p.get_free_models()) == 2

    def test_discover_live_no_free_models_raises(self):
        payload = {"data": [{"id": "paid", "pricing": {"prompt": "1", "completion": "1"}}]}
        fake = MagicMock(status_code=200)
        fake.raise_for_status = lambda: None
        fake.json = lambda: payload
        with patch("src.discovery.live.httpx.get", return_value=fake):
            with pytest.raises(LiveDiscoveryError, match="không trả về model free"):
                discover_live()
