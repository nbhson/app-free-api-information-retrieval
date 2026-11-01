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


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch):
    """
    SSRF guard không resolve DNS thật trong test (test chạy offline, không network):
    mọi hostname thông thường → IP public giả lập. Test SSRF riêng monkeypatch
    lại `src.verification.ssrf.resolve_hostname` để giả lập private IP.
    """
    from src.verification import ssrf

    monkeypatch.setattr(ssrf, "resolve_hostname", lambda hostname: ["93.184.216.34"])
    yield


@pytest.fixture(autouse=True)
def _shared_source_opt_out(monkeypatch):
    """
    Nguồn 'shared' (opt-in only) mặc định TẮT cho mọi test — không leak trạng thái
    opt-in (flag CLI/env INCLUDE_SHARED) hay cờ "đã cảnh báo" giữa các test.
    """
    import src.discovery.websearch.backends as backends

    monkeypatch.setattr(backends, "_shared_cli_opt_in", False)
    monkeypatch.setattr(backends, "_shared_warning_shown", False)
    monkeypatch.delenv(backends.SHARED_OPT_IN_ENV, raising=False)
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
