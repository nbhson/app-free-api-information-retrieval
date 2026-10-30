"""Shared pytest fixtures."""

import pytest

from src.config import get_storage_config
from src.models import APIStyle, AuthType, Provider, ProviderStatus


@pytest.fixture(autouse=True)
def _tmp_history_db(tmp_path, monkeypatch):
    """Trỏ history DB vào tmp_path cho mọi test — không đụng data/providers.db thật."""
    monkeypatch.setenv("HISTORY_DB_PATH", str(tmp_path / "providers.db"))
    get_storage_config.cache_clear()
    yield
    get_storage_config.cache_clear()


@pytest.fixture(autouse=True)
def _tmp_scan_state(tmp_path, monkeypatch):
    """Trỏ file trạng thái quét vào tmp_path cho mọi test — không đụng data/scan_state.json thật."""
    monkeypatch.setenv("SCAN_STATE_PATH", str(tmp_path / "scan_state.json"))
    yield


@pytest.fixture
def sample_provider() -> Provider:
    return Provider(
        name="Test Provider",
        base_url="https://api.example.com/v1",
        website="https://example.com",
        description="Test provider",
        models=[
            {"id": "model-free", "name": "Free Model", "is_free": True},
            {"id": "model-paid", "name": "Paid Model", "is_free": False},
        ],
        status=ProviderStatus.ACTIVE,
        auth_type=AuthType.API_KEY,
        api_style=APIStyle.OPENAI,
        auth_required=True,
        tags=["test"],
    )


@pytest.fixture
def sample_providers(sample_provider: Provider) -> list[Provider]:
    other = sample_provider.model_copy(deep=True)
    other.name = "Other Provider"
    other.base_url = "https://api2.example.com/v1"
    return [sample_provider, other]
