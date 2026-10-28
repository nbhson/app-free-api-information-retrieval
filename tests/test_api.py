"""Tests cho src.api.app (FastAPI TestClient — không chạy server thật, không gọi mạng)."""

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from fastapi.testclient import TestClient  # noqa: E402

from src.__version__ import __version__  # noqa: E402
from src.api.app import app  # noqa: E402


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
