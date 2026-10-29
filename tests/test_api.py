"""Tests cho src.api.app (FastAPI TestClient — không chạy server thật, không gọi mạng)."""

from typing import Any

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from fastapi.testclient import TestClient  # noqa: E402

from src.__version__ import __version__  # noqa: E402
from src.api.app import app  # noqa: E402
from src.config import get_api_config  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestRoot:
    def test_root_shows_api_info(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Free LLM Provider Discovery API"
        assert data["version"] == __version__
        assert "/api/v1/providers" in " ".join(data["endpoints"])


class TestVersion:
    def test_version_endpoint(self, client):
        resp = client.get("/api/v1/version")
        assert resp.status_code == 200
        assert resp.json()["version"] == __version__


class TestListProviders:
    def test_list_all_providers(self, client):
        resp = client.get("/api/v1/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] >= 15
        assert len(data["providers"]) == data["total_count"]

    def test_list_only_free_models_by_default(self, client):
        resp = client.get("/api/v1/providers")
        for p in resp.json()["providers"]:
            assert all(m["is_free"] for m in p["models"]), p["name"]

    def test_include_paid_models(self, client):
        resp = client.get("/api/v1/providers", params={"free_only": "false"})
        data = resp.json()
        # Together AI / Replicate chỉ có model paid — phải xuất hiện khi free_only=false
        names = {p["name"] for p in data["providers"]}
        assert "Together AI" in names
        together = next(p for p in data["providers"] if p["name"] == "Together AI")
        assert any(not m["is_free"] for m in together["models"])

    def test_filter_by_tag(self, client):
        resp = client.get("/api/v1/providers", params={"tag": "free-tier"})
        data = resp.json()
        assert data["total_count"] >= 3
        assert "Groq" in {p["name"] for p in data["providers"]}

    def test_filter_no_auth(self, client):
        resp = client.get("/api/v1/providers", params={"no_auth": "true"})
        data = resp.json()
        assert all(p["auth_required"] is False for p in data["providers"])
        assert "Ollama" in {p["name"] for p in data["providers"]}

    def test_filter_combined(self, client):
        resp = client.get(
            "/api/v1/providers", params={"tag": "openai-compatible", "no_auth": "true"}
        )
        data = resp.json()
        for p in data["providers"]:
            assert "openai-compatible" in p["tags"]
            assert p["auth_required"] is False


class TestGetProvider:
    def test_get_existing_provider(self, client):
        resp = client.get("/api/v1/providers/groq")  # case-insensitive
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Groq"
        assert data["base_url"] == "https://api.groq.com/openai/v1"
        assert len(data["models"]) >= 1

    def test_get_provider_case_insensitive(self, client):
        assert client.get("/api/v1/providers/GROQ").status_code == 200
        assert client.get("/api/v1/providers/Groq").status_code == 200

    def test_get_missing_provider_404(self, client):
        resp = client.get("/api/v1/providers/nonexistent-xyz")
        assert resp.status_code == 404
        assert "không tồn tại" in resp.json()["detail"]

    def test_detail_includes_paid_models(self, client):
        """Chi tiết provider phải gồm cả model paid (để người dùng biết đầy đủ)."""
        resp = client.get("/api/v1/providers/replicate")
        assert resp.status_code == 200
        models = resp.json()["models"]
        assert any(not m["is_free"] for m in models)


class TestHealth:
    def test_health_endpoint(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["registry"]["total_providers"] >= 15
        assert "ai_configured" in data
        assert data["version"] == __version__


class TestNewProvidersInRegistry:
    """Provider mới (part3) phải xuất hiện trong API."""

    def test_cloudflare_in_registry(self, client):
        resp = client.get("/api/v1/providers/Cloudflare Workers AI")
        assert resp.status_code == 200
        assert resp.json()["api_style"] == "openai"

    def test_replicate_is_paid_only(self, client):
        resp = client.get("/api/v1/providers/replicate")
        assert resp.status_code == 200
        assert all(not m["is_free"] for m in resp.json()["models"])

    def test_github_models_free(self, client):
        resp = client.get("/api/v1/providers/GitHub Models")
        assert resp.status_code == 200
        assert any(m["is_free"] for m in resp.json()["models"])

    def test_cerebras_and_sambanova_free(self, client):
        for name in ("Cerebras", "SambaNova"):
            resp = client.get(f"/api/v1/providers/{name}")
            assert resp.status_code == 200, name
            assert any(m["is_free"] for m in resp.json()["models"]), name


class TestPagination:
    def test_meta_present_and_defaults(self, client):
        resp = client.get("/api/v1/providers")
        data = resp.json()
        assert "meta" in data
        assert data["meta"]["total"] == data["total_count"]
        assert data["meta"]["count"] == len(data["providers"])
        assert data["meta"]["limit"] == 100  # default
        assert data["meta"]["offset"] == 0

    def test_limit_caps_returned_providers(self, client):
        resp = client.get("/api/v1/providers", params={"limit": 5, "offset": 0})
        data = resp.json()
        assert len(data["providers"]) == 5
        assert data["meta"]["count"] == 5
        assert data["meta"]["total"] > 5  # registry lớn hơn page size

    def test_offset_pages_through_results(self, client):
        first = client.get("/api/v1/providers", params={"limit": 5, "offset": 0}).json()
        second = client.get("/api/v1/providers", params={"limit": 5, "offset": 5}).json()
        names_page1 = {p["name"] for p in first["providers"]}
        names_page2 = {p["name"] for p in second["providers"]}
        assert names_page1.isdisjoint(names_page2)  # không trùng giữa 2 trang

    def test_limit_max_100(self, client):
        resp = client.get("/api/v1/providers", params={"limit": 101})
        assert resp.status_code == 422  # validation chặn limit > 100

    def test_limit_zero_rejected(self, client):
        assert client.get("/api/v1/providers", params={"limit": 0}).status_code == 422

    def test_negative_offset_rejected(self, client):
        assert client.get("/api/v1/providers", params={"offset": -1}).status_code == 422

    def test_pages_count(self, client):
        data = client.get("/api/v1/providers", params={"limit": 10, "offset": 0}).json()
        total = data["meta"]["total"]
        assert data["meta"]["pages"] == -(-total // 10)  # ceil


class TestProviderHistory:
    def test_history_unknown_provider_404(self, client):
        resp = client.get("/api/v1/providers/nonexistent-xyz/history")
        assert resp.status_code == 404

    def test_history_empty_when_no_checks(self, client):
        """Provider tồn tại trong registry nhưng chưa verify lần nào → lịch sử rỗng."""
        resp = client.get("/api/v1/providers/groq/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "Groq"
        assert data["history"] == []
        assert data["total_checks"] == 0
        assert data["uptime_percent"] is None

    def test_history_after_verify(self, client, tmp_path, sample_provider):
        """Sau khi record snapshot, endpoint trả lịch sử + uptime đúng."""
        from src.config import get_storage_config
        from src.storage.history import HistoryStore

        store = HistoryStore(get_storage_config().db_path)
        store.record("Groq", "active", latency_ms=10.0)
        store.record("Groq", "inactive")
        store.record("Groq", "active")

        resp = client.get("/api/v1/providers/groq/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_checks"] == 3
        assert data["active_count"] == 2
        assert data["uptime_percent"] == 66.67
        assert len(data["history"]) == 3
        assert data["history"][0]["status"] in {"active", "inactive"}

    def test_history_limit_param(self, client):
        from src.config import get_storage_config
        from src.storage.history import HistoryStore

        store = HistoryStore(get_storage_config().db_path)
        for _ in range(5):
            store.record("Groq", "active")
        resp = client.get("/api/v1/providers/groq/history", params={"limit": 2})
        assert len(resp.json()["history"]) == 2


class TestAPIKeyAuth:
    """API key auth optional — bật khi API_KEYS env được set."""

    @pytest.fixture
    def auth_client(self, monkeypatch) -> TestClient:
        monkeypatch.setenv("API_KEYS", "secret1,secret2")
        get_api_config.cache_clear()
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def _reset_api_config(self):
        """Đảm bảo config singleton được reset sau mỗi test trong class này."""
        yield
        get_api_config.cache_clear()

    def test_public_by_default(self, client):
        """Không set API_KEYS → API public (behavior cũ giữ nguyên)."""
        assert client.get("/api/v1/providers").status_code == 200
        assert client.get("/api/v1/providers/groq").status_code == 200

    def test_401_without_key_when_enabled(self, auth_client):
        resp = auth_client.get("/api/v1/providers")
        assert resp.status_code == 401
        assert "X-API-Key" in resp.json()["detail"]

    def test_401_with_wrong_key(self, auth_client):
        resp = client_get(auth_client, "/api/v1/providers", key="wrong")
        assert resp.status_code == 401

    def test_200_with_valid_key(self, auth_client):
        resp = client_get(auth_client, "/api/v1/providers", key="secret1")
        assert resp.status_code == 200

    def test_all_keys_valid(self, auth_client):
        assert client_get(auth_client, "/api/v1/providers", key="secret2").status_code == 200

    def test_health_and_version_stay_public(self, auth_client):
        """Health/version/docs luôn public kể cả khi auth bật."""
        assert auth_client.get("/api/v1/health").status_code == 200
        assert auth_client.get("/api/v1/version").status_code == 200
        assert auth_client.get("/").status_code == 200

    def test_detail_endpoint_requires_key(self, auth_client):
        assert client_get(auth_client, "/api/v1/providers/groq", key=None).status_code == 401
        assert client_get(auth_client, "/api/v1/providers/groq", key="secret1").status_code == 200


def client_get(client: TestClient, path: str, key: str | None) -> Any:
    headers = {"X-API-Key": key} if key else {}
    return client.get(path, headers=headers)
