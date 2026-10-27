"""Tests cho src.discovery registry."""
import pytest

from src.discovery import (
    KNOWN_PROVIDERS, PROVIDER_REGISTRY,
    get_provider_by_name, get_providers_by_tag, get_providers_no_auth,
)


class TestRegistry:
    def test_has_providers(self):
        assert len(KNOWN_PROVIDERS) >= 10

    def test_unique_names(self):
        names = [p.name for p in KNOWN_PROVIDERS]
        assert len(names) == len(set(names)), f"Duplicate provider names: {names}"

    def test_all_have_base_url(self):
        for p in KNOWN_PROVIDERS:
            assert p.base_url.startswith(("http://", "https://")), p.name

    def test_all_have_at_least_one_model(self):
        for p in KNOWN_PROVIDERS:
            assert len(p.models) >= 1, f"{p.name} has no models"

    def test_get_provider_by_name_case_insensitive(self):
        assert get_provider_by_name("GROQ") is not None
        assert get_provider_by_name("groq") is not None
        assert get_provider_by_name("nonexistent-xyz") is None

    def test_get_providers_by_tag(self):
        free_tier = get_providers_by_tag("free-tier")
        assert len(free_tier) >= 3

    def test_get_providers_no_auth(self):
        no_auth = get_providers_no_auth()
        assert all(not p.auth_required for p in no_auth)


class TestDataConsistency:
    """Đảm bảo dữ liệu registry nhất quán với mô tả free/paid."""

    def test_trial_only_providers_marked_not_free(self):
        """Provider tag 'trial-only' phải có is_free=False trên models."""
        for p in KNOWN_PROVIDERS:
            if "trial-only" in p.tags:
                for m in p.models:
                    assert m.is_free is False, (
                        f"{p.name} tagged trial-only nhưng model {m.id} is_free=True"
                    )

    def test_free_tier_providers_have_free_models(self):
        """Provider tag 'free-tier' phải có ít nhất 1 model is_free=True."""
        for p in KNOWN_PROVIDERS:
            if "free-tier" in p.tags:
                assert any(m.is_free for m in p.models), (
                    f"{p.name} tagged free-tier nhưng không có model free"
                )

    def test_base_urls_are_https(self):
        for p in KNOWN_PROVIDERS:
            assert p.base_url.startswith("https://"), (
                f"{p.name} dùng URL không an toàn: {p.base_url}"
            )
