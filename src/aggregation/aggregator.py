"""
Aggregator - Tổng hợp danh sách provider và xuất ra file
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional

import yaml

from src.models import Provider, ProviderList


def aggregate_providers(providers: List[Provider]) -> ProviderList:
    """Tổng hợp danh sách provider thành ProviderList"""
    return ProviderList(
        providers=providers,
        last_updated=datetime.now(timezone.utc),
    )


def _provider_to_dict(provider: Provider) -> dict:
    data = provider.model_dump(mode="json")
    # Chỉ giữ free models nếu muốn lọc sau
    return data


def save_to_json(provider_list: ProviderList, path: str, only_free: bool = True) -> str:
    """Lưu danh sách provider ra file JSON"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "last_updated": provider_list.last_updated.isoformat(),
        "total_count": len(provider_list.providers),
        "providers": [],
    }
    for prov in provider_list.providers:
        entry = prov.model_dump(mode="json")
        if only_free:
            entry["models"] = [m for m in entry["models"] if m["is_free"]]
        payload["providers"].append(entry)

    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(p)


def save_to_yaml(provider_list: ProviderList, path: str, only_free: bool = True) -> str:
    """Lưu danh sách provider ra file YAML"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    data = {"providers": []}
    for prov in provider_list.providers:
        entry = prov.model_dump(mode="json")
        if only_free:
            entry["models"] = [m for m in entry["models"] if m["is_free"]]
        data["providers"].append(entry)

    p.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return str(p)
