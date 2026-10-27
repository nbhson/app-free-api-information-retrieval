"""Tests cho src.models."""
from datetime import datetime, timezone

from src.models import (
    Model, Provider, ProviderList, ProviderStatus, AuthType, APIStyle,
)


class TestModel:
    def test_default_is_free(self):
        m = Model(id="x", name="X")
        assert m.is_free is True

    def test_explicit_not_free(self):
        m = Model(id="x", name="X", is_free=False)
        assert m.is_free is False


class TestProvider:
    def test_get_free_models_filters_correctly(self, sample_provider):
        free = sample_provider.get_free_models()
        assert [m.id for m in free] == ["model-free"]

    def test_default_status_unknown(self):
        p = Provider(name="N", base_url="https://x.com/v1")
        assert p.status == ProviderStatus.UNKNOWN

    def test_tags_default_empty(self):
        p = Provider(name="N", base_url="https://x.com/v1")
        assert p.tags == []

    def test_model_dump_roundtrip(self, sample_provider):
        data = sample_provider.model_dump(mode="json")
        restored = Provider.model_validate(data)
        assert restored.name == sample_provider.name
        assert len(restored.models) == 2


class TestProviderList:
    def test_total_count_auto(self, sample_providers):
        pl = ProviderList(providers=sample_providers)
        assert pl.total_count == 2
        assert pl.version == "1.0.0"

    def test_last_updated_is_timezone_aware(self, sample_providers):
        pl = ProviderList(providers=sample_providers)
        assert pl.last_updated.tzinfo is not None
        assert isinstance(pl.last_updated, datetime)

    def test_empty_list(self):
        pl = ProviderList()
        assert pl.total_count == 0
        assert pl.providers == []


class TestEnums:
    def test_auth_values(self):
        assert AuthType.NONE == "none"
        assert AuthType.API_KEY == "api_key"

    def test_api_style_values(self):
        assert APIStyle.OPENAI == "openai"
        assert APIStyle.ANTHROPIC == "anthropic"
        assert APIStyle.CUSTOM == "custom"
