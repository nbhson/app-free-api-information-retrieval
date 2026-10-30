"""Tests cho CLI (click.testing.CliRunner, mock network)."""

import json

import pytest
from click.testing import CliRunner

from src.cli.main import cli
from src.models import ProviderStatus
from src.verification import SmokeTestError


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_verify(monkeypatch):
    """Mock verify_* để không gọi mạng thật — trả về copy, không mutate registry."""
    import src.cli.main as m

    async def fake_verify_one(prov, timeout=10.0, retries=2, api_key=None, parse_models=False):
        result = prov.model_copy(deep=True)
        result.status = ProviderStatus.ACTIVE
        return result

    async def fake_verify_all(provs, progress_callback=None):
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

    def test_list_csv_has_header_and_rows(self, runner):
        result = runner.invoke(cli, ["list", "--format", "csv"])
        assert result.exit_code == 0
        lines = [ln for ln in result.output.strip().splitlines() if ln]
        assert len(lines) >= 2  # header + ít nhất 1 row
        assert "provider" in lines[0]
        assert "model_id" in lines[0]
        assert "Groq" in result.output

    def test_list_csv_parses_with_csv_module(self, runner):
        import csv as csv_module
        import io as io_module

        result = runner.invoke(cli, ["list", "--format", "csv"])
        assert result.exit_code == 0
        rows = list(csv_module.DictReader(io_module.StringIO(result.output)))
        assert len(rows) >= 10
        assert all("provider" in r and "model_id" in r for r in rows)

    def test_list_output_saves_file_with_csv_format(self, runner, tmp_path):
        out = tmp_path / "providers.csv"
        result = runner.invoke(cli, ["list", "--format", "csv", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        content = out.read_text()
        assert "provider" in content.splitlines()[0]

    def test_list_output_csv_by_extension_only(self, runner, tmp_path):
        """--output file.csv tự chọn CSV kể cả khi --format table."""
        out = tmp_path / "providers.csv"
        result = runner.invoke(cli, ["list", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        assert out.read_text().startswith("provider")

    def test_list_verify_flag(self, runner, mock_verify):
        result = runner.invoke(cli, ["list", "--verify"])
        assert result.exit_code == 0
        assert "active" in result.output


class TestCheckCommand:
    def test_check_not_found_exits_1(self, runner):
        result = runner.invoke(cli, ["check", "--provider", "nonexistent-xyz"])
        assert result.exit_code == 1
        assert "Không tìm thấy" in result.output

    def test_check_suggests_similar_providers(self, runner):
        """Khi gõ sai tên provider, CLI phải gợi ý gần đúng."""
        result = runner.invoke(cli, ["check", "--provider", "grop"])  # typo of "groq"
        assert result.exit_code == 1
        assert "Groq" in result.output  # gợi ý đúng

    def test_check_success_shows_active(self, runner, mock_verify):
        result = runner.invoke(cli, ["check", "--provider", "groq"])
        assert result.exit_code == 0
        assert "active" in result.output.lower()

    def test_check_writes_history_to_db(self, runner, mock_verify):
        """Lệnh check phải ghi snapshot verify vào SQLite (HISTORY_DB_PATH)."""
        import os

        from src.config import get_storage_config
        from src.storage.history import HistoryStore

        runner.invoke(cli, ["check", "--provider", "groq"])
        db_path = get_storage_config().db_path
        assert os.path.exists(db_path), "check không ghi DB theo HISTORY_DB_PATH"
        store = HistoryStore(db_path)
        recs = store.get_history("Groq")
        assert len(recs) == 1
        assert recs[0].status == "active"
        assert recs[0].latency_ms is not None  # check đo latency


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

    def test_update_writes_history_for_all_providers(self, runner, mock_verify):
        """Lệnh update ghi snapshot cho từng provider vào DB."""
        from src.config import get_storage_config
        from src.discovery import KNOWN_PROVIDERS
        from src.storage.history import HistoryStore

        runner.invoke(cli, ["update", "--output", "out.json"])
        store = HistoryStore(get_storage_config().db_path)
        assert store.count() >= len(KNOWN_PROVIDERS)


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
        assert "rate_limited" in result.output.lower()


class TestListVerifyExitCode:
    def test_list_verify_exit_0_when_all_active(self, runner, mock_verify):
        result = runner.invoke(cli, ["list", "--verify"])
        assert result.exit_code == 0

    def test_list_verify_exit_1_when_inactive_found(self, runner, monkeypatch):
        import src.cli.main as m

        async def fake_some_inactive(provs, progress_callback=None):
            result = []
            for p in provs:
                cp = p.model_copy(deep=True)
                cp.status = ProviderStatus.INACTIVE if p.name == "Groq" else ProviderStatus.ACTIVE
                result.append(cp)
            return result

        monkeypatch.setattr(m, "verify_all_providers", fake_some_inactive)
        result = runner.invoke(cli, ["list", "--verify"])
        assert result.exit_code == 1
        assert result.exception is None or isinstance(result.exception, SystemExit)


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


class TestVersionFlag:
    def test_version_flag_shows_version(self, runner):
        """CLI phải có --version flag lấy version từ single source."""
        from src.__version__ import __version__

        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_cli_version_shows_prog_name(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert "free-llm-provider-discovery" in result.output


class TestServeCommand:
    def test_serve_help_shows_options(self, runner):
        result = runner.invoke(cli, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output

    def test_serve_defaults(self, runner):
        result = runner.invoke(cli, ["serve", "--help"])
        assert "127.0.0.1" in result.output
        assert "8000" in result.output


class TestVerboseFlag:
    def test_list_verbose_flag_accepted(self, runner):
        result = runner.invoke(cli, ["list", "--verbose"])
        assert result.exit_code == 0
        assert "Free LLM Providers" in result.output

    def test_list_verbose_short_flag(self, runner):
        result = runner.invoke(cli, ["list", "-v"])
        assert result.exit_code == 0


class TestDiscoverLiveCommand:
    @pytest.fixture
    def mock_live(self, monkeypatch):
        """Mock discover_live để không gọi mạng thật."""
        import src.cli.main as m
        from src.discovery.live import build_openrouter_live_provider
        from src.models import Model

        def fake_discover_live():
            models = [
                Model(id="meta-llama/llama-3.1-8b:free", name="Llama 3.1 8B", is_free=True),
                Model(id="mistralai/mistral-7b:free", name="Mistral 7B", is_free=True),
            ]
            return build_openrouter_live_provider(models)

        monkeypatch.setattr(m, "discover_live", fake_discover_live)

    def test_discover_live_shows_table(self, runner, mock_live):
        result = runner.invoke(cli, ["discover-live"])
        assert result.exit_code == 0
        assert "OpenRouter" in result.output
        assert "2" in result.output  # 2 model free

    def test_discover_live_error_exits_1(self, runner, monkeypatch):
        import src.cli.main as m
        from src.discovery.live import LiveDiscoveryError

        def fake_error():
            raise LiveDiscoveryError("Timeout")

        monkeypatch.setattr(m, "discover_live", fake_error)
        result = runner.invoke(cli, ["discover-live"])
        assert result.exit_code == 1
        assert "Lỗi live discovery" in result.output

    def test_discover_live_saves_output(self, runner, tmp_path, mock_live):
        out = tmp_path / "live.json"
        result = runner.invoke(cli, ["discover-live", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["total_count"] == 1
        assert data["providers"][0]["name"] == "OpenRouter"
        assert len(data["providers"][0]["models"]) == 2


class TestListVerifyOutputRegression:
    def test_list_verify_output_saves_file_even_with_inactive(self, runner, tmp_path, monkeypatch):
        """Regression: --output phải được lưu kể cả khi có provider chết (exit code 1).

        Trước fix, sys.exit(1) chạy trước khi lưu file → CI mất toàn bộ dữ liệu verify.
        """
        import src.cli.main as m

        async def fake_some_inactive(provs, progress_callback=None):
            result = []
            for p in provs:
                cp = p.model_copy(deep=True)
                cp.status = ProviderStatus.INACTIVE if p.name == "Groq" else ProviderStatus.ACTIVE
                result.append(cp)
            return result

        monkeypatch.setattr(m, "verify_all_providers", fake_some_inactive)
        out = tmp_path / "verified.json"
        result = runner.invoke(cli, ["list", "--verify", "--output", str(out)])
        assert result.exit_code == 1  # vẫn exit 1 cho CI/hooks
        assert out.exists(), "--output bị mất khi exit 1 (bug cũ)"
        data = json.loads(out.read_text())
        assert data["total_count"] >= 10
        # Provider chết vẫn có trong file với status inactive
        groq = next(p for p in data["providers"] if p["name"] == "Groq")
        assert groq["status"] == "inactive"


class TestCheckDeepVerify:
    """check --api-key / --sync-models / --smoke: deep verification."""

    def test_check_sync_models_shows_live_list(self, runner, monkeypatch):
        import src.cli.main as m

        async def fake_verify(prov, timeout=10.0, retries=2, api_key=None, parse_models=False):
            result = prov.model_copy(deep=True)
            result.status = ProviderStatus.ACTIVE
            if parse_models:
                from src.models import Model

                result.models = [
                    Model(id="live-a", name="Live A"),
                    Model(id="live-b", name="Live B"),
                ]
            return result

        monkeypatch.setattr(m, "verify_provider", fake_verify)
        result = runner.invoke(cli, ["check", "-p", "groq", "--sync-models"])
        assert result.exit_code == 0
        assert "live-a" in result.output
        assert "live-b" in result.output

    def test_check_smoke_requires_api_key(self, runner, mock_verify):
        result = runner.invoke(cli, ["check", "-p", "groq", "--smoke", "some-model"])
        assert result.exit_code == 1
        assert "--api-key" in result.output

    def test_check_smoke_success(self, runner, mock_verify, monkeypatch):
        import src.cli.main as m

        async def fake_smoke(prov, model_id, api_key=None, prompt="", **kw):
            return {
                "content": "OK",
                "model": model_id,
                "latency_ms": 123.4,
                "finish_reason": "stop",
                "usage": {"total_tokens": 10},
            }

        monkeypatch.setattr(m, "smoke_test_chat", fake_smoke)
        result = runner.invoke(
            cli, ["check", "-p", "groq", "--api-key", "sk-test", "--smoke", "llama-3"]
        )
        assert result.exit_code == 0
        assert "Smoke test OK" in result.output
        assert "OK" in result.output

    def test_check_smoke_failure_exits_1(self, runner, mock_verify, monkeypatch):
        import src.cli.main as m

        async def fake_smoke_fail(prov, model_id, api_key=None, prompt="", **kw):
            raise SmokeTestError(f"HTTP 401 từ provider (model={model_id})")

        monkeypatch.setattr(m, "smoke_test_chat", fake_smoke_fail)
        result = runner.invoke(
            cli, ["check", "-p", "groq", "--api-key", "sk-test", "--smoke", "llama-3"]
        )
        assert result.exit_code == 1
        assert "Smoke test thất bại" in result.output

    def test_check_api_key_passed_to_verifier(self, runner, monkeypatch):
        """--api-key phải được forward vào verify_provider."""
        import src.cli.main as m

        captured: dict = {}

        async def fake_verify(prov, timeout=10.0, retries=2, api_key=None, parse_models=False):
            captured["api_key"] = api_key
            captured["parse_models"] = parse_models
            result = prov.model_copy(deep=True)
            result.status = ProviderStatus.ACTIVE
            return result

        monkeypatch.setattr(m, "verify_provider", fake_verify)
        result = runner.invoke(
            cli, ["check", "-p", "groq", "--api-key", "sk-secret", "--sync-models"]
        )
        assert result.exit_code == 0
        assert captured["api_key"] == "sk-secret"
        assert captured["parse_models"] is True

    def test_check_api_key_from_env(self, runner, monkeypatch):
        """Env PROVIDER_API_KEY được dùng khi không có --api-key."""
        import src.cli.main as m

        captured: dict = {}

        async def fake_verify(prov, timeout=10.0, retries=2, api_key=None, parse_models=False):
            captured["api_key"] = api_key
            result = prov.model_copy(deep=True)
            result.status = ProviderStatus.ACTIVE
            return result

        monkeypatch.setattr(m, "verify_provider", fake_verify)
        monkeypatch.setenv("PROVIDER_API_KEY", "sk-from-env")
        result = runner.invoke(cli, ["check", "-p", "groq"])
        assert result.exit_code == 0
        assert captured["api_key"] == "sk-from-env"


class TestUpstageInRegistry:
    """Upstage provider mới thêm vào registry — đúng metadata và model đã test thật."""

    def test_upstage_exists(self):
        from src.discovery import get_provider_by_name

        p = get_provider_by_name("upstage")
        assert p is not None
        assert p.base_url == "https://api.upstage.ai/v1"
        assert p.status == ProviderStatus.ACTIVE
        assert p.api_style.value == "openai"

    def test_upstage_has_solar_pro4(self):
        from src.discovery import get_provider_by_name

        p = get_provider_by_name("upstage")
        model_ids = [m.id for m in p.models]
        assert "solar-pro4" in model_ids
        assert "solar-mini4" in model_ids
