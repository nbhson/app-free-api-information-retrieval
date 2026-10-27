"""Tests cho src.aggregation.aggregator (không gọi mạng)."""
import json
import tempfile
from pathlib import Path

from src.models import Model, Provider, ProviderStatus, AuthType, APIStyle
from src.aggregation import aggregator


def _minimal_provider() -> Provider:
    return Provider(
        name="Mini",
        base_url="https://api.test.com/v1",
        models=[{"id": "free-m", "name": "Free M", "is_free": True}],
        status=ProviderStatus.ACTIVE,
        auth_type=AuthType.API_KEY,
        api_style=APIStyle.OPENAI,
        auth_required=True,
        tags=["test"],
    )


class TestAggregate:
    def test_returns_provider_list(self):
        p = _minimal_provider()
        result = aggregator.aggregate_providers([p])
        assert len(result.providers) == 1
        assert result.total_count == 1

    def test_last_updated_has_timezone(self):
        result = aggregator.aggregate_providers([_minimal_provider()])
        assert result.last_updated.tzinfo is not None


class TestSaveJson:
    def test_saves_free_models_only(self, tmp_path):
        p = _minimal_provider()
        p.models.append(
            Model(id="paid-m", name="Paid M", is_free=False)
        )
        pl = aggregator.aggregate_providers([p])
        path = tmp_path / "out.json"
        aggregator.save_to_json(pl, str(path))
        data = json.loads(path.read_text())
        assert data["total_count"] == 1
        assert all(m["is_free"] for m in data["providers"][0]["models"])

    def test_creates_parent_dir(self, tmp_path):
        pl = aggregator.aggregate_providers([_minimal_provider()])
        path = tmp_path / "deep/nested/out.json"
        aggregator.save_to_json(pl, str(path))
        assert path.exists()

    def test_iso_format_timestamp(self, tmp_path):
        pl = aggregator.aggregate_providers([_minimal_provider()])
        path = tmp_path / "out.json"
        aggregator.save_to_json(pl, str(path))
        data = json.loads(path.read_text())
        assert "T" in data["last_updated"]


class TestSaveYaml:
    def test_yaml_roundtrip(self, tmp_path):
        pl = aggregator.aggregate_providers([_minimal_provider()])
        path = tmp_path / "out.yaml"
        aggregator.save_to_yaml(pl, str(path))
        assert path.exists()
        content = path.read_text()
        assert "Mini" in content
        assert "free-m" in content
