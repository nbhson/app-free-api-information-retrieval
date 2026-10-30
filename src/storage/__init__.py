"""
Storage Module — Lưu trữ lịch sử verify provider (SQLite, stdlib only).
"""

from .history import HistoryRecord, HistoryStore, record_provider_history
from .scan_state import ScanState

__all__ = ["HistoryRecord", "HistoryStore", "ScanState", "record_provider_history"]
