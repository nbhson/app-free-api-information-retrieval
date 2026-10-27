"""Tests cho CLI (click.testing.CliRunner, mock network)."""

import json

import pytest
from click.testing import CliRunner

from src.cli.main import cli
from src.models import ProviderStatus


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_verify(monkeypatch):
    """Mock verify_* để không gọi mạng thật."""
    import src.cli.main as m

    async def fake_verify_one(prov, timeout=10.0, retries=2):
        prov.status = ProviderStatus.ACTIVE
        return prov

    async def fake_verify_all(provs):
        for p in provs:
            p.status = ProviderStatus.ACTIVE
        return list(provs)

    monkeypatch.setattr(m, "verify_provider", fake_verify_one)
    monkeypatch.setattr(m, "verify_all_providers", fake_verify_all)


class TestListCommand:
    def test_list_table(self, runner):
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "Free LLM Providers" in result.output

    def test_list_json_valid(self, runner):
        result = runner.invoke(cli, ["list", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 10

    def test_list_output_saves_file_with_json_format(self, runner, tmp_path):
        """Regression test: --output phải hoạt động kể cả với --format json."""
        out = tmp_path / "providers_out.json"
        result = runner.invoke(cli, ["list", "--format", "json", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists(), "--output bị bỏ qua khi --format json (bug cũ)"
        data = json.loads(out.read_text())
        assert data["total_count"] >= 10

    def test_list_output_saves_file_with_yaml_format(self, runner, tmp_path):
        out = tmp_path / "providers.yaml"
        result = runner.invoke(cli, ["list", "--format", "yaml", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()

    def test_list_tag_filter(self, runner):
        result = runner.invoke(cli, ["list", "--tag", "free-tier"])
        assert result.exit_code == 0
        assert "Groq" in result.output

    def test_list_verify_flag(self, runner, mock_verify):
        result = runner.invoke(cli, ["list", "--verify"])
        assert result.exit_code == 0
        assert "active" in result.output


class TestCheckCommand:
    def test_check_not_found_exits_1(self, runner):
        result = runner.invoke(cli, ["check", "--provider", "nonexistent-xyz"])
        assert result.exit_code == 1
        assert "Không tìm thấy" in result.output

    def test_check_success_shows_active(self, runner, mock_verify):
        result = runner.invoke(cli, ["check", "--provider", "groq"])
        assert result.exit_code == 0
        assert "ACTIVE" in result.output


class TestUpdateCommand:
    def test_update_creates_output_file(self, runner, tmp_path, mock_verify):
        out = tmp_path / "out.json"
        result = runner.invoke(cli, ["update", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["total_count"] >= 10

    def test_update_yaml_extension(self, runner, tmp_path, mock_verify):
        out = tmp_path / "out.yaml"
        result = runner.invoke(cli, ["update", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        assert "providers:" in out.read_text()
