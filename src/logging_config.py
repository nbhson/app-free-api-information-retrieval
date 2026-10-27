"""
Structured logging cho application — dùng stdlib logging (không thêm dep).
"""

import logging
import sys
from typing import Literal


def setup_logging(level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO") -> None:
    """Thiết lập structured logging cho toàn bộ app."""
    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
        root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
