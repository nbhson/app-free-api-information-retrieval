"""Tests cho src.config."""

import pytest
from pydantic import ValidationError

from src.config import AIConfig, get_ai_config


class TestAIConfig:
    def test_defaults(self):
        cfg = AIConfig(AI_PROVIDER_BASE_URL="", AI_API_KEY="", AI_MODEL="")
        assert cfg.timeout == 60  # default
        assert cfg.is_configured() is False

    def test_is_configured_true_when_all_set(self):
        cfg = AIConfig(
            AI_PROVIDER_BASE_URL="https://x.com/v1",
            AI_API_KEY="sk-x",
            AI_MODEL="m",
        )
        assert cfg.is_configured() is True

    def test_base_url_strips_trailing_slash(self):
        cfg = AIConfig(AI_PROVIDER_BASE_URL="https://x.com/v1/", AI_API_KEY="k", AI_MODEL="m")
        assert cfg.base_url == "https://x.com/v1"

    def test_invalid_base_url_rejected(self):
        with pytest.raises(ValidationError):
            AIConfig(AI_PROVIDER_BASE_URL="ftp://bad", AI_API_KEY="k", AI_MODEL="m")

    def test_validate_lists_missing_fields(self):
        cfg = AIConfig(AI_PROVIDER_BASE_URL="", AI_API_KEY="k", AI_MODEL="")
        errors = cfg.validation_errors()
        assert len(errors) == 2  # base_url + api_key (model được set nên không lỗi)

    def test_validate_ok_when_configured(self):
        cfg = AIConfig(AI_PROVIDER_BASE_URL="https://x.com/v1", AI_API_KEY="k", AI_MODEL="m")
        assert cfg.validation_errors() == []

    def test_timeout_must_be_positive(self):
        with pytest.raises(ValidationError):
            AIConfig(
                AI_PROVIDER_BASE_URL="https://x.com/v1", AI_API_KEY="k", AI_MODEL="m", AI_TIMEOUT=0
            )

    def test_negative_timeout_rejected(self):
        with pytest.raises(ValidationError):
            AIConfig(
                AI_PROVIDER_BASE_URL="https://x.com/v1",
                AI_API_KEY="k",
                AI_MODEL="m",
                AI_TIMEOUT=-5,
            )


class TestGetAiConfig:
    def test_returns_cached_singleton(self):
        assert get_ai_config() is get_ai_config()
