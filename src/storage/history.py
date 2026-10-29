"""
History — Lưu snapshot kết quả verify provider vào SQLite (stdlib sqlite3, không thêm dep).

Mỗi lần verify (CLI `check` / `update` hoặc API) ghi 1 dòng snapshot:
provider_name, status, latency_ms, checked_at, models_count, error.

Dùng cho:
- GET /api/v1/providers/{name}/history  — lịch sử + uptime%
- CLI check/update — ghi DB tự động
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_storage_config
from src.models import Provider

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS verify_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms REAL,
    checked_at TEXT NOT NULL,
    models_count INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_provider
    ON verify_history (provider_name, checked_at);
"""


@dataclass(frozen=True)
class HistoryRecord:
    """Một dòng snapshot kết quả verify."""

    provider_name: str
    status: str
    checked_at: str
    latency_ms: float | None = None
    models_count: int = 0
    error: str | None = None


class HistoryStore:
    """
    Store lịch sử verify trên SQLite.

    Mỗi thao tác mở connection riêng (an toàn khi dùng từ FastAPI threadpool
    và CLI đồng thời), tự tạo bảng nếu chưa có.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        # None = đọc từ settings (env HISTORY_DB_PATH, default data/providers.db)
        self.db_path = Path(db_path) if db_path is not None else get_storage_config().db_path

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript(_SCHEMA)
        return conn

    def record(
        self,
        provider_name: str,
        status: str,
        latency_ms: float | None = None,
        models_count: int = 0,
        error: str | None = None,
        checked_at: str | None = None,
    ) -> HistoryRecord:
        """Ghi một snapshot kết quả verify. Trả về record đã lưu."""
        record = HistoryRecord(
            provider_name=provider_name,
            status=status,
            checked_at=checked_at or datetime.now(timezone.utc).isoformat(),
            latency_ms=latency_ms,
            models_count=models_count,
            error=error,
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO verify_history "
                "(provider_name, status, latency_ms, checked_at, models_count, error) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.provider_name,
                    record.status,
                    record.latency_ms,
                    record.checked_at,
                    record.models_count,
                    record.error,
                ),
            )
        return record

    def record_provider(self, provider: Provider, latency_ms: float | None = None) -> HistoryRecord:
        """Ghi snapshot từ một Provider đã verify."""
        return self.record(
            provider_name=provider.name,
            status=provider.status.value,
            latency_ms=latency_ms,
            models_count=len(provider.models),
            error=None,
        )

    def get_history(
        self, provider_name: str, limit: int | None = None, offset: int = 0
    ) -> list[HistoryRecord]:
        """
        Lấy lịch sử verify của một provider (mới nhất trước).

        Args:
            provider_name: Tên provider (so khớp chính xác, case-insensitive).
            limit: Số dòng tối đa (None = tất cả).
            offset: Bỏ qua N dòng đầu (phân trang).
        """
        query = (
            "SELECT provider_name, status, latency_ms, checked_at, models_count, error "
            "FROM verify_history WHERE provider_name = ? COLLATE NOCASE "
            "ORDER BY checked_at DESC, id DESC"
        )
        params: list[str | int] = [provider_name]
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            HistoryRecord(
                provider_name=row[0],
                status=row[1],
                latency_ms=row[2],
                checked_at=row[3],
                models_count=row[4],
                error=row[5],
            )
            for row in rows
        ]

    def get_uptime(self, provider_name: str) -> dict[str, int | float | None]:
        """
        Thống kê uptime của provider: số lần ACTIVE / tổng số lần check.

        Trả về {"total_checks": n, "active_count": k, "uptime_percent": k/n*100}.
        uptime_percent = None nếu chưa có lần verify nào.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*), "
                "SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) "
                "FROM verify_history WHERE provider_name = ? COLLATE NOCASE",
                (provider_name,),
            ).fetchone()
        total = int(row[0]) if row and row[0] is not None else 0
        active = int(row[1]) if row and row[1] is not None else 0
        uptime = round(active / total * 100, 2) if total > 0 else None
        return {"total_checks": total, "active_count": active, "uptime_percent": uptime}

    def count(self, provider_name: str | None = None) -> int:
        """Số snapshot đã lưu (toàn bộ DB, hoặc theo provider)."""
        with self._connect() as conn:
            if provider_name is None:
                row = conn.execute("SELECT COUNT(*) FROM verify_history").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM verify_history "
                    "WHERE provider_name = ? COLLATE NOCASE",
                    (provider_name,),
                ).fetchone()
        return int(row[0]) if row else 0


def record_provider_history(provider: Provider, latency_ms: float | None = None) -> None:
    """
    Ghi snapshot verify của provider vào DB (theo path từ settings).

    Không bao giờ raise — lỗi DB chỉ log warning để không làm fail CLI/API.
    """
    try:
        HistoryStore().record_provider(provider, latency_ms=latency_ms)
    except sqlite3.Error as e:
        logger.warning("Không ghi được lịch sử verify cho %s: %s", provider.name, e)
