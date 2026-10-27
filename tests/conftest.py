"""Shared pytest fixtures."""
import pytest
from src.models import Provider, Model, ProviderStatus, AuthType, APIStyle


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
