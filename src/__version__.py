"""
Single source of truth cho version của ứng dụng.

Ưu tiên đọc từ metadata của package đã install (pyproject.toml → importlib.metadata).
Fallback: parse trực tiếp pyproject.toml (chạy từ source, chưa pip install).
"""

from __future__ import annotations

import re
from pathlib import Path

_FALLBACK_VERSION = "0.0.0"
_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _version_from_metadata() -> str | None:
    """Đọc version từ metadata của package đã pip install."""
    try:
        from importlib.metadata import version

        return version("free-llm-provider-discovery")
    except Exception:  # noqa: BLE001 — mọi lỗi metadata đều fallback
        return None


def _version_from_pyproject() -> str | None:
    """Parse version trực tiếp từ pyproject.toml (khi chạy từ source)."""
    try:
        text = _PYPROJECT.read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        return match.group(1) if match else None
    except OSError:
        return None


def _resolve_version() -> str:
    return _version_from_metadata() or _version_from_pyproject() or _FALLBACK_VERSION


__version__ = _resolve_version()
