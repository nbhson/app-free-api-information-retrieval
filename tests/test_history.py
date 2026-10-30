"""Tests cho src.storage.history (SQLite, tmp_path — không đụng DB thật)."""

import sqlite3

import pytest

from src.models import ProviderStatus
from src.storage.history import HistoryStore, record_provider_history


@pytest.fixture
def store(tmp_path) -> HistoryStore:
    return HistoryStore(tmp_path / "test.db")


class TestRecord:
    def test_record_and_read_back(self, store):
        store.record(
            provider_name="Groq",
            status="active",
            latency_ms=123.45,
            models_count=3,
            checked_at="2026-01-01T00:00:00+00:00",
        )
        history = store.get_history("groq")  # case-insensitive
        assert len(history) == 1
        rec = history[0]
        assert rec.provider_name == "Groq"
        assert rec.status == "active"
        assert rec.latency_ms == 123.45
        assert rec.models_count == 3
        assert rec.error is None

    def test_multiple_records_ordered_newest_first(self, store):
        store.record("P", "active", checked_at="2026-01-01T00:00:00+00:00")
        store.record("P", "inactive", checked_at="2026-01-02T00:00:00+00:00")
        history = store.get_history("P")
        assert len(history) == 2
        assert history[0].status == "inactive"  # mới nhất trước
        assert history[1].status == "active"

    def test_history_scoped_by_provider(self, store):
        store.record("P1", "active")
        store.record("P2", "inactive")
        assert store.get_history("P1")[0].provider_name == "P1"
        assert len(store.get_history("P2")) == 1

    def test_error_field_persisted(self, store):
        store.record("P", "unknown", error="Timeout sau 10s")
        assert store.get_history("P")[0].error == "Timeout sau 10s"

    def test_auto_checked_at(self, store):
        rec = store.record("P", "active")
        assert "T" in rec.checked_at  # ISO format


class TestUptime:
    def test_uptime_percent_mixed_statuses(self, store):
        for status in ("active", "active", "active", "inactive"):
            store.record("P", status)
        stats = store.get_uptime("P")
        assert stats["total_checks"] == 4
        assert stats["active_count"] == 3
        assert stats["uptime_percent"] == 75.0

    def test_uptime_all_active(self, store):
        store.record("P", "active")
        store.record("P", "active")
        assert store.get_uptime("P")["uptime_percent"] == 100.0

    def test_uptime_no_data_is_none(self, store):
        stats = store.get_uptime("never-checked")
        assert stats == {"total_checks": 0, "active_count": 0, "uptime_percent": None}

    def test_uptime_case_insensitive_name(self, store):
        store.record("Groq", "active")
        assert store.get_uptime("GROQ")["total_checks"] == 1


class TestPagination:
    def test_limit_and_offset(self, store):
        for _ in range(10):
            store.record("P", "active")
        page = store.get_history("P", limit=3, offset=2)
        assert len(page) == 3

    def test_count(self, store):
        store.record("P", "active")
        store.record("P", "inactive")
        store.record("Q", "active")
        assert store.count() == 3
        assert store.count("P") == 2


class TestRecordProvider:
    def test_from_provider_object(self, store, sample_provider):
        store.record_provider(sample_provider, latency_ms=42.5)
        recs = store.get_history(sample_provider.name)
        assert len(recs) == 1
        assert recs[0].status == ProviderStatus.ACTIVE.value
        assert recs[0].latency_ms == 42.5
        assert recs[0].models_count == 2  # 2 models trong fixture

    def test_record_provider_history_never_raises(self, sample_provider, monkeypatch):
        """Lỗi DB (sqlite3.Error) chỉ log warning, không crash CLI/API."""
        from src.storage import history as h

        def boom(self, provider, latency_ms=None):
            raise sqlite3.OperationalError("boom")

        monkeypatch.setattr(h.HistoryStore, "record_provider", boom)
        # Không raise
        record_provider_history(sample_provider)


class TestConnectionClosed:
    def test_connection_closed_after_each_operation(self, store, monkeypatch):
        """Regression: connection phải được đóng sau mỗi thao tác (không phụ thuộc GC)."""
        from src.storage import history as history_module

        created = []
        orig_connect = history_module.sqlite3.connect

        def tracking_connect(*args, **kwargs):
            conn = orig_connect(*args, **kwargs)
            created.append(conn)
            return conn

        monkeypatch.setattr(history_module.sqlite3, "connect", tracking_connect)

        store.record("P", "active")
        store.get_history("P")
        store.get_uptime("P")
        store.count()

        assert len(created) == 4
        for conn in created:
            # Connection đã close → mọi query raise ProgrammingError
            with pytest.raises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")
