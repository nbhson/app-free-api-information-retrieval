"""
Aggregator - Tổng hợp danh sách provider và xuất ra file
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

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


def _filter_free_models(entry: dict) -> dict:
    """Trả về entry với chỉ models free (nếu chỉ_free). Helper dùng chung JSON/YAML."""
    entry["models"] = [m for m in entry["models"] if m["is_free"]]
    return entry


def _save_payload(payload: dict, path: Path, as_yaml: bool) -> Path:
    """Ghi payload ra file, tạo parent dir nếu cần."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if as_yaml:
        path.write_text(yaml.dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def save_to_json(provider_list: ProviderList, path: str, only_free: bool = True) -> str:
    """Lưu danh sách provider ra file JSON"""
    payload = {
        "version": provider_list.version,
        "last_updated": provider_list.last_updated.isoformat(),
        "total_count": len(provider_list.providers),
        "providers": [],
    }
    for prov in provider_list.providers:
        entry = prov.model_dump(mode="json")
        if only_free:
            entry = _filter_free_models(entry)
        payload["providers"].append(entry)

    return str(_save_payload(payload, Path(path), as_yaml=False))


def save_to_yaml(provider_list: ProviderList, path: str, only_free: bool = True) -> str:
    """Lưu danh sách provider ra file YAML"""
    data = {
        "version": provider_list.version,
        "providers": [],
    }
    for prov in provider_list.providers:
        entry = prov.model_dump(mode="json")
        if only_free:
            entry = _filter_free_models(entry)
        data["providers"].append(entry)

    return str(_save_payload(data, Path(path), as_yaml=True))
