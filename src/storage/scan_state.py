"""
ScanState — Trạng thái quét internet giữa các lần chạy (JSON file, không thêm dep).

Mục đích: mỗi lần `discover-web` quét xong, lưu lại toàn bộ tiến trình:
- `seen_urls`: các URL kết quả search ĐÃ xử lý → lần sau bỏ qua, chỉ xem trang mới
- `used_keywords`: từ khoá ĐÃ search → lần sau xoay vòng sang từ khoá chưa dùng
- `providers`: toàn bộ provider đã tìm thấy (tích luỹ qua các lần chạy)

Nhờ vậy lần chạy sau tiếp tục từ nơi đã dừng và tìm thêm trang web MỚI
có free token, thay vì quét lại từ đầu và ra kết quả trùng lặp.

File mặc định: data/scan_state.json (config qua env SCAN_STATE_PATH).
Lỗi file trạng thái (mất/hỏng/sai định dạng) KHÔNG BAO GIỜ crash —
reset về trạng thái rỗng với warning, pipeline vẫn chạy bình thường.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.models import Provider

logger = logging.getLogger(__name__)

DEFAULT_STATE_PATH = Path("data") / "scan_state.json"
ENV_STATE_PATH = "SCAN_STATE_PATH"


def _default_path() -> Path:
    """Đường dẫn mặc định: env SCAN_STATE_PATH (cho test/CLI tùy chỉnh) hoặc data/scan_state.json."""
    env = os.environ.get(ENV_STATE_PATH, "")
    return Path(env) if env else DEFAULT_STATE_PATH


_STATE_VERSION = 2  # v2: thêm run_history (timestamp từng lần scan) + merge cập nhật info


class ScanState:
    """
    Trạng thái quét tích luỹ giữa các lần chạy discover-web.

    Dùng như context manager để tự động lưu khi thoát khối `with` —
    kể cả khi giữa chừng có exception, tiến trình vẫn không mất.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else _default_path()
        self.seen_urls: set[str] = set()
        self.used_keywords: set[str] = set()
        self.providers: list[Provider] = []
        self.last_run_at: str | None = None
        # Lịch sử các lần scan (timestamp + keyword + số provider mới/cập nhật)
        # — giúp phân biệt các lần quét và debug việc chạy lại cùng keyword
        self.run_history: list[dict[str, Any]] = []
        # Provider ĐÃ CÓ được cập nhật info ở lần merge gần nhất (không phải thêm mới)
        self.last_merge_updated: list[Provider] = []

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path | None = None) -> ScanState:
        """
        Đọc trạng thái từ file. File không tồn tại / lỗi / sai schema
        → trả về trạng thái rỗng (chỉ log warning, không raise).
        """
        state = cls(path)
        if not state.path.exists():
            return state
        try:
            raw = json.loads(state.path.read_text(encoding="utf-8"))
            state.seen_urls = {u.lower() for u in raw.get("seen_urls", []) if u}
            state.used_keywords = {k.lower() for k in raw.get("used_keywords", []) if k}
            state.providers = [Provider.model_validate(p) for p in raw.get("providers", []) if p]
            state.last_run_at = raw.get("last_run_at")
            state.run_history = raw.get("run_history", [])
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as e:
            logger.warning("File trạng thái %s lỗi (%s) — reset về rỗng", state.path, e)
            state = cls(path)
        return state

    def save(self) -> Path:
        """Ghi trạng thái ra file (atomic qua file tạm + rename)."""
        self.last_run_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "version": _STATE_VERSION,
            "last_run_at": self.last_run_at,
            "seen_urls": sorted(self.seen_urls),
            "used_keywords": sorted(self.used_keywords),
            "total_providers": len(self.providers),
            # run_history: timestamp từng lần scan để phân biệt các lần quét
            "run_history": self.run_history[-50:],
            "providers": [p.model_dump(mode="json") for p in self.providers],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
        return self.path

    def __enter__(self) -> ScanState:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Luôn lưu khi thoát `with` — lỗi save chỉ warning, không che exception gốc."""
        try:
            self.save()
        except OSError as e:  # pragma: no cover — đĩa đầy / permission
            logger.warning("Không lưu được trạng thái %s: %s", self.path, e)

    # ------------------------------------------------------------------
    # Cập nhật trạng thái
    # ------------------------------------------------------------------

    def mark_seen_urls(self, urls: list[str]) -> int:
        """Đánh dấu các URL kết quả search đã xử lý. Trả về số URL mới được thêm."""
        before = len(self.seen_urls)
        self.seen_urls.update(u.lower() for u in urls if u)
        return len(self.seen_urls) - before

    def filter_new_urls(self, items: list) -> list:
        """Lọc list[SearchResult] — chỉ giữ URL chưa từng xử lý (URL mới)."""
        new_items = [r for r in items if r.url.lower() not in self.seen_urls]
        skipped = len(items) - len(new_items)
        if skipped:
            logger.info("Bỏ qua %d URL đã xử lý ở lần chạy trước", skipped)
        return new_items

    def pick_fresh_keywords(
        self, pool: list[str], user_keywords: list[str], batch_size: int = 8
    ) -> list[str]:
        """
        Chọn từ khoá cho lần chạy này (cơ chế xoay vòng):
        - Người dùng truyền keyword cụ thể → dùng luôn toàn bộ.
        - Không truyền → lấy tối đa `batch_size` từ khoá CHƯA dùng trong pool
          (mỗi lần quét khai thác một vùng mới; pool cạn thì bắt đầu chu kỳ mới).
        """
        if user_keywords:
            return user_keywords
        used = {k.lower() for k in self.used_keywords}
        fresh = [k for k in pool if k.lower() not in used]
        if not fresh:
            # Mọi từ khoá đã dùng hết 1 vòng → bắt đầu chu kỳ mới từ đầu pool
            fresh = list(pool)
        return fresh[:batch_size]

    def merge_providers(
        self, new_providers: list[Provider], update_existing: bool = True
    ) -> list[Provider]:
        """
        Gộp provider vào kho tích luỹ:
        - Provider MỚI (theo base_url/name) → thêm vào kho, trả về trong kết quả.
        - Provider ĐÃ CÓ + update_existing=True → cập nhật thông tin (models,
          description, website, tags) nhưng GIỮ nguyên status verify và tag
          cũ để không mất trạng thái — được tính vào `self.last_merge_updated`.
        - Provider ĐÃ CÓ + update_existing=False → bỏ qua như cũ.

        Returns:
            Danh sách provider MỚI THẬT SỰ thêm vào (chưa có trước đó).
            Số provider được cập nhật info nằm ở `self.last_merge_updated`.
        """
        self.last_merge_updated = []
        existing_by_url = {p.base_url.lower(): p for p in self.providers}
        existing_by_name = {p.name.lower(): p for p in self.providers}
        added: list[Provider] = []
        for p in new_providers:
            old = existing_by_url.get(p.base_url.lower()) or existing_by_name.get(p.name.lower())
            if old is not None:
                if update_existing:
                    self._refresh_provider(old, p)
                    self.last_merge_updated.append(old)
                continue
            existing_by_url[p.base_url.lower()] = p
            existing_by_name[p.name.lower()] = p
            self.providers.append(p)
            added.append(p)
        return added

    @staticmethod
    def _refresh_provider(old: Provider, new: Provider) -> None:
        """Cập nhật info của provider đã có từ dữ liệu tìm lại — giữ status verify cũ."""
        if new.models:
            old.models = new.models
        if new.description and new.description != old.description:
            old.description = new.description
        if new.website and new.website != old.website:
            old.website = new.website
        for t in new.tags:
            if t not in old.tags:
                old.tags.append(t)

    def record_run(
        self, keywords: list[str], added: int, updated: int, mode: str
    ) -> dict[str, Any]:
        """Ghi 1 entry lịch sử cho lần scan vừa xong (timestamp + kết quả)."""
        entry: dict[str, Any] = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "keywords": keywords,
            "new_providers": added,
            "updated_providers": updated,
        }
        self.run_history.append(entry)
        return entry

    def stats(self) -> dict[str, int | str | None]:
        """Tóm tắt trạng thái (hiển thị CLI): số URL/keyword/provider đã tích luỹ."""
        free_models = sum(len(p.get_free_models()) for p in self.providers)
        return {
            "seen_urls": len(self.seen_urls),
            "used_keywords": len(self.used_keywords),
            "providers": len(self.providers),
            "free_models": free_models,
            "last_run_at": self.last_run_at,
        }
