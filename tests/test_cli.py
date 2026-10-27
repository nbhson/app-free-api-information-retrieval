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
    """Mock verify_* để không gọi mạng thật — trả về copy, không mutate registry."""
    import src.cli.main as m

    async def fake_verify_one(prov, timeout=10.0, retries=2):
        result = prov.model_copy(deep=True)
        result.status = ProviderStatus.ACTIVE
        return result

    async def fake_verify_all(provs):
        results = []
        for p in provs:
            cp = p.model_copy(deep=True)
            cp.status = ProviderStatus.ACTIVE
            results.append(cp)
        return results

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


class TestHealthCommand:
    def test_health_shows_table(self, runner):
        result = runner.invoke(cli, ["health"])
        assert result.exit_code == 0
        assert "Health Check" in result.output
        assert "Registry:" in result.output
        assert "Version:" in result.output
        assert "AI Configured:" in result.output

    def test_health_saves_json(self, runner, tmp_path):
        out = tmp_path / "health.json"
        result = runner.invoke(cli, ["health", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert "status" in data
        assert "registry" in data
        assert data["registry"]["total_providers"] >= 10
        assert "version" in data
        assert "ai_configured" in data

    def test_health_warnings_for_unknown_providers(self, runner):
        result = runner.invoke(cli, ["health"])
        # Ollama, GigaChat, Yandex có status UNKNOWN → warnings
        assert "Warnings:" in result.output or "chưa được verify" in result.output


class TestCheckExitCodes:
    def test_check_exit_0_on_active(self, runner, mock_verify):
        result = runner.invoke(cli, ["check", "--provider", "groq"])
        assert result.exit_code == 0

    def test_check_exit_1_on_inactive(self, runner, monkeypatch):
        import src.cli.main as m
        from src.models import Provider

        async def fake_inactive(prov, **kw):
            result = prov.model_copy(deep=True)
            result.status = ProviderStatus.INACTIVE
            return result

        monkeypatch.setattr(m, "verify_provider", fake_inactive)
        result = runner.invoke(cli, ["check", "--provider", "groq"])
        assert result.exit_code == 1

    def test_check_exit_2_on_rate_limited(self, runner, monkeypatch):
        import src.cli.main as m

        async def fake_rl(prov, **kw):
            result = prov.model_copy(deep=True)
            result.status = ProviderStatus.RATE_LIMITED
            return result

        monkeypatch.setattr(m, "verify_provider", fake_rl)
        result = runner.invoke(cli, ["check", "--provider", "groq"])
        assert result.exit_code == 2
        assert "RATE_LIMITED" in result.output


class TestListVerifyExitCode:
    def test_list_verify_exit_0_when_all_active(self, runner, mock_verify):
        result = runner.invoke(cli, ["list", "--verify"])
        assert result.exit_code == 0

    def test_list_verify_exit_1_when_inactive_found(self, runner, monkeypatch):
        import src.cli.main as m

        async def fake_some_inactive(provs):
            from src.models import Provider
            result = []
            for p in provs:
                cp = p.model_copy(deep=True)
                cp.status = ProviderStatus.INACTIVE if p.name == "Groq" else ProviderStatus.ACTIVE
                result.append(cp)
            return result

        monkeypatch.setattr(m, "verify_all_providers", fake_some_inactive)
        result = runner.invoke(cli, ["list", "--verify"])
        assert result.exit_code == 1


class TestDiscoverAIDedup:
    def test_discover_ai_dedup_filters_known_provider(self, runner, monkeypatch):
        """Provider đã có trong registry → bị lọc bỏ, hiện cảnh báo."""
        import src.cli.main as m
        from src.models import Model, Provider, ProviderStatus

        def fake_discover(cfg):
            # AI trả về Groq (đã tồn tại trong registry)
            return [
                Provider(
                    name="Groq",
                    base_url="https://api.groq.com/openai/v1",
                    models=[Model(id="llama-3.1-8b-instant", name="Llama", is_free=True)],
                    status=ProviderStatus.UNKNOWN,
                )
            ]

        monkeypatch.setattr(m, "discover_with_ai", fake_discover)
        result = runner.invoke(cli, ["discover-ai", "--show"])
        assert result.exit_code == 0
        # Groq bị lọc → AI thông báo không có kết quả hợp lệ
        assert "trùng lặp" in result.output or "không trả về" in result.output


class TestVerboseFlag:
    def test_list_verbose_flag_accepted(self, runner):
        result = runner.invoke(cli, ["list", "--verbose"])
        assert result.exit_code == 0
        assert "Free LLM Providers" in result.output

    def test_list_verbose_short_flag(self, runner):
        result = runner.invoke(cli, ["list", "-v"])
        assert result.exit_code == 0
