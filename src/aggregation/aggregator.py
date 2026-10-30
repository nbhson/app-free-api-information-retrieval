"""
Aggregator - Tổng hợp danh sách provider và xuất ra file
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.__version__ import __version__
from src.models import Provider, ProviderList


def aggregate_providers(providers: list[Provider]) -> ProviderList:
    """Tổng hợp danh sách provider thành ProviderList"""
    return ProviderList(
        providers=providers,
        last_updated=datetime.now(timezone.utc),
        version=__version__,
    )


def _filter_free_models(entry: dict[str, Any]) -> dict[str, Any]:
    """Trả về entry với chỉ models free. Helper dùng chung JSON/YAML."""
    entry["models"] = [m for m in entry["models"] if m["is_free"]]
    return entry


def _save_payload(payload: dict[str, Any], path: Path, as_yaml: bool) -> Path:
    """Ghi payload ra file, tạo parent dir nếu cần."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if as_yaml:
        path.write_text(yaml.dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def save_to_json(provider_list: ProviderList, path: str, only_free: bool = True) -> str:
    """Lưu danh sách provider ra file JSON"""
    payload: dict[str, Any] = {
        "version": provider_list.version,
        "last_updated": provider_list.last_updated.isoformat(),
        "total_count": len(provider_list.providers),
        "providers": [],
    }
    for prov in provider_list.providers:
        entry: dict[str, Any] = prov.model_dump(mode="json")
        if only_free:
            entry = _filter_free_models(entry)
        payload["providers"].append(entry)

    return str(_save_payload(payload, Path(path), as_yaml=False))


def save_to_yaml(provider_list: ProviderList, path: str, only_free: bool = True) -> str:
    """Lưu danh sách provider ra file YAML"""
    data: dict[str, Any] = {
        "version": provider_list.version,
        "providers": [],
    }
    for prov in provider_list.providers:
        entry: dict[str, Any] = prov.model_dump(mode="json")
        if only_free:
            entry = _filter_free_models(entry)
        data["providers"].append(entry)

    return str(_save_payload(data, Path(path), as_yaml=True))


# Cột CSV — 1 row cho mỗi cặp (provider, model), thân thiện với spreadsheet
CSV_COLUMNS = [
    "provider",
    "base_url",
    "status",
    "auth_required",
    "api_style",
    "tags",
    "model_id",
    "model_name",
    "is_free",
    "context_length",
    "supports_streaming",
    "rate_limit",
    "last_updated",
]


def _csv_rows(provider_list: ProviderList, only_free: bool) -> list[dict[str, Any]]:
    """Flatten provider + model thành rows cho CSV."""
    rows: list[dict[str, Any]] = []
    for prov in provider_list.providers:
        base = {
            "provider": prov.name,
            "base_url": prov.base_url,
            "status": prov.status.value,
            "auth_required": prov.auth_required,
            "api_style": prov.api_style.value,
            "tags": ", ".join(prov.tags),
            "rate_limit": prov.rate_limit or "",
            "last_updated": provider_list.last_updated.isoformat(),
        }
        models = prov.get_free_models() if only_free else prov.models
        if not models:
            # Provider không có model (sau lọc) — vẫn xuất 1 row để không mất dữ liệu
            rows.append(
                {
                    **base,
                    "model_id": "",
                    "model_name": "",
                    "is_free": "",
                    "context_length": "",
                    "supports_streaming": "",
                }
            )
            continue
        for model in models:
            rows.append(
                {
                    **base,
                    "model_id": model.id,
                    "model_name": model.name,
                    "is_free": model.is_free,
                    "context_length": model.context_length if model.context_length else "",
                    "supports_streaming": model.supports_streaming,
                }
            )
    return rows


def providers_to_csv(provider_list: ProviderList, only_free: bool = True) -> str:
    """Tạo chuỗi CSV từ danh sách provider (mỗi model 1 row) — dùng cho stdout."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(_csv_rows(provider_list, only_free))
    return buf.getvalue()


def save_to_csv(provider_list: ProviderList, path: str, only_free: bool = True) -> str:
    """Lưu danh sách provider ra file CSV (mỗi model 1 row) — mở được bằng Excel/Sheets."""
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(providers_to_csv(provider_list, only_free), encoding="utf-8")
    return str(path_obj)
