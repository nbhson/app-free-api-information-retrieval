"""Tests cho src.aggregation.aggregator (không gọi mạng)."""

import json

from src.aggregation import aggregator
from src.models import APIStyle, AuthType, Model, Provider, ProviderStatus


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
        p.models.append(Model(id="paid-m", name="Paid M", is_free=False))
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


class TestCsv:
    def test_csv_header_and_rows(self, tmp_path):
        pl = aggregator.aggregate_providers([_minimal_provider()])
        path = tmp_path / "out.csv"
        aggregator.save_to_csv(pl, str(path))
        content = path.read_text()
        lines = content.strip().splitlines()
        assert lines[0].startswith("provider")
        assert "Mini" in content
        assert "free-m" in content
        assert len(lines) == 2  # header + 1 model

    def test_csv_creates_parent_dir(self, tmp_path):
        pl = aggregator.aggregate_providers([_minimal_provider()])
        path = tmp_path / "deep/nested/out.csv"
        aggregator.save_to_csv(pl, str(path))
        assert path.exists()

    def test_csv_only_free_models(self, tmp_path):
        p = _minimal_provider()
        p.models.append(Model(id="paid-m", name="Paid M", is_free=False))
        pl = aggregator.aggregate_providers([p])
        path = tmp_path / "out.csv"
        aggregator.save_to_csv(pl, str(path))
        assert "paid-m" not in path.read_text()

    def test_csv_include_paid_when_disabled(self, tmp_path):
        p = _minimal_provider()
        p.models.append(Model(id="paid-m", name="Paid M", is_free=False))
        pl = aggregator.aggregate_providers([p])
        path = tmp_path / "out.csv"
        aggregator.save_to_csv(pl, str(path), only_free=False)
        assert "paid-m" in path.read_text()

    def test_providers_to_csv_string_roundtrip(self):
        """CSV xuất ra string parse được bằng csv.DictReader."""
        import csv as csv_module
        import io as io_module

        p = _minimal_provider()
        pl = aggregator.aggregate_providers([p])
        text = aggregator.providers_to_csv(pl)
        rows = list(csv_module.DictReader(io_module.StringIO(text)))
        assert len(rows) == 1
        assert rows[0]["provider"] == "Mini"
        assert rows[0]["model_id"] == "free-m"
        assert rows[0]["is_free"] == "True"

    def test_csv_one_row_per_model(self):
        import csv as csv_module
        import io as io_module

        p = _minimal_provider()
        p.models.append(Model(id="free-m2", name="Free M2", is_free=True))
        pl = aggregator.aggregate_providers([p])
        text = aggregator.providers_to_csv(pl)
        rows = list(csv_module.DictReader(io_module.StringIO(text)))
        assert len(rows) == 2
        assert {r["model_id"] for r in rows} == {"free-m", "free-m2"}


class TestCsvModelLessProvider:
    def test_provider_without_free_models_still_gets_row(self):
        """Regression: provider không có model free vẫn xuất 1 row CSV (không mất dữ liệu)."""
        import csv as csv_module
        import io as io_module

        p = _minimal_provider()
        p.models = [Model(id="paid-m", name="Paid M", is_free=False)]
        pl = aggregator.aggregate_providers([p])
        text = aggregator.providers_to_csv(pl)  # only_free=True mặc định
        rows = list(csv_module.DictReader(io_module.StringIO(text)))
        assert len(rows) == 1
        assert rows[0]["provider"] == "Mini"
        assert rows[0]["model_id"] == ""
        assert rows[0]["base_url"] == "https://api.test.com/v1"

    def test_provider_without_any_models_still_gets_row(self, tmp_path):
        p = _minimal_provider()
        p.models = []
        pl = aggregator.aggregate_providers([p])
        path = tmp_path / "out.csv"
        aggregator.save_to_csv(pl, str(path))
        content = path.read_text()
        assert "Mini" in content
        assert len(content.strip().splitlines()) == 2  # header + 1 row trống model
