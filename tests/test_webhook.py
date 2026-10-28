"""Tests cho src.notifications.webhook (mock HTTP, không gọi mạng thật)."""

from unittest.mock import patch

import httpx
import pytest

from src.config import WebhookConfig
from src.models import Provider, ProviderStatus
from src.notifications import detect_status_changes, send_webhook_notification
from src.notifications.webhook import StatusChange, build_payload


def _provider(name: str, status: ProviderStatus) -> Provider:
    return Provider(name=name, base_url=f"https://{name.lower()}.example.com/v1", status=status)


class TestDetectStatusChanges:
    def test_no_change(self):
        originals = [_provider("Groq", ProviderStatus.ACTIVE)]
        verified = [_provider("Groq", ProviderStatus.ACTIVE)]
        assert detect_status_changes(originals, verified) == []

    def test_active_to_inactive(self):
        originals = [_provider("Groq", ProviderStatus.ACTIVE)]
        verified = [_provider("Groq", ProviderStatus.INACTIVE)]
        changes = detect_status_changes(originals, verified)
        assert len(changes) == 1
        assert changes[0].provider == "Groq"
        assert changes[0].old_status == "active"
        assert changes[0].new_status == "inactive"

    def test_unknown_to_active(self):
        originals = [_provider("Ollama", ProviderStatus.UNKNOWN)]
        verified = [_provider("Ollama", ProviderStatus.ACTIVE)]
        changes = detect_status_changes(originals, verified)
        assert len(changes) == 1
        assert changes[0].old_status == "unknown"
        assert changes[0].new_status == "active"

    def test_new_provider_has_unknown_old_status(self):
        """Provider xuất hiện sau verify (không có trong originals) → old_status=unknown."""
        originals: list[Provider] = []
        verified = [_provider("NewGuy", ProviderStatus.RATE_LIMITED)]
        changes = detect_status_changes(originals, verified)
        assert len(changes) == 1
        assert changes[0].old_status == "unknown"
        assert changes[0].new_status == "rate_limited"

    def test_multiple_changes(self):
        originals = [
            _provider("A", ProviderStatus.ACTIVE),
            _provider("B", ProviderStatus.ACTIVE),
        ]
        verified = [
            _provider("A", ProviderStatus.INACTIVE),
            _provider("B", ProviderStatus.ACTIVE),
        ]
        changes = detect_status_changes(originals, verified)
        assert len(changes) == 1
        assert changes[0].provider == "A"


class TestBuildPayload:
    def test_payload_structure(self):
        changes = [
            StatusChange(
                provider="Groq",
                base_url="https://api.groq.com/v1",
                old_status="active",
                new_status="inactive",
            )
        ]
        payload = build_payload(changes)
        assert payload["event"] == "provider_status_changed"
        assert payload["total_changes"] == 1
        assert payload["changes"][0]["provider"] == "Groq"
        assert "version" in payload
        assert "timestamp" in payload


class TestSendWebhook:
    def _cfg(
        self, url: str = "https://hooks.example.com/abc", enabled: bool = True
    ) -> WebhookConfig:
        return WebhookConfig(WEBHOOK_URL=url, WEBHOOK_TIMEOUT=5, WEBHOOK_ENABLED=enabled)

    def test_not_configured_returns_false(self):
        changes = [StatusChange(provider="A", base_url="x", old_status="a", new_status="b")]
        assert send_webhook_notification(changes, self._cfg(url="")) is False

    def test_disabled_returns_false(self):
        changes = [StatusChange(provider="A", base_url="x", old_status="a", new_status="b")]
        assert send_webhook_notification(changes, self._cfg(enabled=False)) is False

    def test_empty_changes_returns_false(self):
        assert send_webhook_notification([], self._cfg()) is False

    def test_success_returns_true(self):
        changes = [StatusChange(provider="A", base_url="x", old_status="a", new_status="b")]
        with patch("src.notifications.webhook.httpx.post") as mock_post:
            mock_post.return_value = httpx.Response(200)
            assert send_webhook_notification(changes, self._cfg()) is True
            assert mock_post.call_count == 1
            assert mock_post.call_args.kwargs["json"]["event"] == "provider_status_changed"

    def test_http_error_returns_false_not_raise(self):
        changes = [StatusChange(provider="A", base_url="x", old_status="a", new_status="b")]
        with patch("src.notifications.webhook.httpx.post") as mock_post:
            mock_post.side_effect = httpx.ConnectError("boom")
            assert send_webhook_notification(changes, self._cfg()) is False

    def test_unexpected_error_returns_false_not_raise(self):
        """Safety net: webhook lỗi không được crash pipeline verify."""
        changes = [StatusChange(provider="A", base_url="x", old_status="a", new_status="b")]
        with patch("src.notifications.webhook.httpx.post") as mock_post:
            mock_post.side_effect = RuntimeError("weird")
            assert send_webhook_notification(changes, self._cfg()) is False

    def test_http_500_returns_false(self):
        changes = [StatusChange(provider="A", base_url="x", old_status="a", new_status="b")]
        with patch("src.notifications.webhook.httpx.post") as mock_post:
            mock_post.return_value = httpx.Response(500)
            assert send_webhook_notification(changes, self._cfg()) is False


class TestWebhookConfig:
    def test_default_not_configured(self):
        cfg = WebhookConfig(WEBHOOK_URL="", WEBHOOK_TIMEOUT=10, WEBHOOK_ENABLED=True)
        assert cfg.is_configured() is False

    def test_configured_with_url(self):
        cfg = WebhookConfig(WEBHOOK_URL="https://hooks.example.com/x", WEBHOOK_ENABLED=True)
        assert cfg.is_configured() is True

    def test_disabled_even_with_url(self):
        cfg = WebhookConfig(WEBHOOK_URL="https://hooks.example.com/x", WEBHOOK_ENABLED=False)
        assert cfg.is_configured() is False

    def test_invalid_url_reported(self):
        cfg = WebhookConfig(WEBHOOK_URL="not-a-url", WEBHOOK_ENABLED=True)
        assert any("WEBHOOK_URL" in e for e in cfg.validation_errors())

    def test_invalid_timeout_rejected(self):
        """WEBHOOK_TIMEOUT <= 0 bị ValidationError (như AI_TIMEOUT)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            WebhookConfig(WEBHOOK_URL="https://x.com", WEBHOOK_TIMEOUT=0, WEBHOOK_ENABLED=True)

        with pytest.raises(ValidationError):
            WebhookConfig(WEBHOOK_TIMEOUT=-5, WEBHOOK_ENABLED=True)


class TestCliWebhookIntegration:
    """CLI phải gọi webhook notification sau khi verify."""

    def test_list_verify_skips_webhook_when_no_change(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        import src.cli.main as m
        from src.cli.main import cli

        async def fake_verify_all(provs, progress_callback=None):
            return [p.model_copy(deep=True) for p in provs]

        sent = {"called": False}

        def fake_send(changes, cfg):
            sent["called"] = True
            return True

        monkeypatch.setattr(m, "verify_all_providers", fake_verify_all)
        monkeypatch.setattr(m, "send_webhook_notification", fake_send)
        result = CliRunner().invoke(cli, ["list", "--verify"])
        assert result.exit_code == 0
        # Registry copy giữ status gốc → không có change → webhook không gửi
        assert sent["called"] is False

    def test_list_verify_sends_webhook_on_change(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        import src.cli.main as m
        from src.cli.main import cli

        async def fake_verify_all(provs, progress_callback=None):
            results = []
            for p in provs:
                cp = p.model_copy(deep=True)
                if p.name == "Groq":
                    cp.status = ProviderStatus.INACTIVE
                results.append(cp)
            return results

        sent = {"changes": None}

        def fake_send(changes, cfg):
            sent["changes"] = changes
            return True

        monkeypatch.setattr(m, "verify_all_providers", fake_verify_all)
        monkeypatch.setattr(m, "send_webhook_notification", fake_send)
        monkeypatch.setattr(
            m, "get_webhook_config", lambda: WebhookConfig(WEBHOOK_URL="https://h.io/x")
        )
        result = CliRunner().invoke(cli, ["list", "--verify"])
        # Groq INACTIVE → exit 1, nhưng webhook vẫn phải được gửi TRƯỚC khi exit
        assert result.exit_code == 1
        assert sent["changes"] is not None
        assert any(c.provider == "Groq" for c in sent["changes"])

    def test_no_crash_when_webhook_fails(self, monkeypatch):
        """Webhook gửi fail → CLI vẫn chạy tiếp, không crash."""
        from click.testing import CliRunner

        import src.cli.main as m
        from src.cli.main import cli

        async def fake_verify_all(provs, progress_callback=None):
            results = []
            for p in provs:
                cp = p.model_copy(deep=True)
                if p.name == "Groq":
                    cp.status = ProviderStatus.INACTIVE
                results.append(cp)
            return results

        def fake_send(changes, cfg):
            return False

        monkeypatch.setattr(m, "verify_all_providers", fake_verify_all)
        monkeypatch.setattr(m, "send_webhook_notification", fake_send)
        monkeypatch.setattr(
            m, "get_webhook_config", lambda: WebhookConfig(WEBHOOK_URL="https://h.io/x")
        )
        result = CliRunner().invoke(cli, ["list", "--verify"])
        assert result.exit_code == 1  # Groq inactive → exit 1 như cũ
        assert "thất bại" in result.output
