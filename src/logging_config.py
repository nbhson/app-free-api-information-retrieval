"""
Structured logging cho application — dùng stdlib logging (không thêm dep).

Design goals:
- Idempotent: gọi nhiều lần setup_logging() vẫn cho kết quả nhất quán.
- Mỗi call reset hoàn toàn root logger → tránh duplicate handler.
- Handler level đồng bộ với root level.
- pytest caplog tương thích: không set propagate=False.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Literal


def setup_logging(level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO") -> None:
    """
    Thiết lập structured logging cho toàn bộ app.

    Idempotent — gọi nhiều lần với level khác nhau vẫn hoạt động đúng.
    Xoá toàn bộ handler cũ của root logger trước khi thêm mới.
    """
    # Xác định numeric level
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    # Xoá toàn bộ handler cũ (tránh duplicate / level drift)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(numeric_level)

    # Thêm handler mới
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(numeric_level)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Lấy logger theo tên module. Auto-setup default logging nếu chưa có."""
    root = logging.getLogger()
    if not root.handlers:
        setup_logging("WARNING")
    return logging.getLogger(name)
