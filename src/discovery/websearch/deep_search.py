"""
Deep Search orchestration — pipeline hoàn chỉnh:

    keywords → search nhiều nguồn (Reddit/HN/DDD/GitHub) → extract (heuristic/AI)
    → dedupe nội bộ + với registry → list[Provider] mới

Kết quả vẫn phải qua pipeline verify (`list --verify`) để lọc provider chết —
web search chỉ là điểm xuất phát, không phải kết luận cuối cùng.
"""

from rich.console import Console

from src.config import AIConfig, get_ai_config
from src.discovery import KNOWN_PROVIDERS
from src.discovery.websearch.backends import SearchResult, run_search
from src.discovery.websearch.extractor import (
    collect_page_contexts,
    extract_heuristic,
    extract_with_ai,
)
from src.models import Provider

console = Console()


class DeepSearchError(Exception):
    """Lỗi khi chạy deep search."""


def dedupe_providers(
    providers: list[Provider], existing: list[Provider] | None = None
) -> list[Provider]:
    """
    Loại provider trùng (theo base_url hoặc name, không phân biệt hoa thường).

    - `existing` là danh sách đã biết (registry) — provider trùng bị loại
    - Trùng nội bộ trong `providers` — giữ cái đầu tiên
    """
    seen_urls: set[str] = set()
    seen_names: set[str] = set()
    for p in existing or []:
        seen_urls.add(p.base_url.lower())
        seen_names.add(p.name.lower())

    unique: list[Provider] = []
    for p in providers:
        if p.base_url.lower() in seen_urls or p.name.lower() in seen_names:
            continue
        seen_urls.add(p.base_url.lower())
        seen_names.add(p.name.lower())
        unique.append(p)
    return unique


def run_deep_search(
    keywords: list[str],
    sources: list[str] | None = None,
    max_results: int = 10,
    timeout: float = 15.0,
    mode: str = "heuristic",  # "heuristic" | "ai"
    ai_config: AIConfig | None = None,
    max_pages: int = 5,
) -> list[Provider]:
    """
    Chạy deep search đầy đủ: search → extract → dedupe với registry.

    Args:
        keywords: Danh sách từ khoá (đã expand).
        sources: Nguồn search (None = tất cả).
        max_results: Số kết quả tối đa mỗi (nguồn × keyword).
        timeout: Timeout mỗi HTTP request.
        mode: 'heuristic' (không cần key) hoặc 'ai' (đọc nội dung trang thật).
        ai_config: Config AI (bắt buộc khi mode='ai').
        max_pages: Số trang tối đa fetch cho AI mode.

    Returns:
        Danh sách provider mới (đã loại trùng với registry), tag 'web-discovered'.
    """
    console.print("[bold]Đang search trên các nguồn:[/bold] " + ", ".join(sources or ["all"]))
    results: list[SearchResult] = run_search(keywords, sources, max_results, timeout)
    console.print(f"[dim]Tổng cộng {len(results)} kết quả thô từ internet[/dim]")

    if mode == "ai":
        cfg = ai_config or get_ai_config()
        if not cfg.is_configured():
            console.print(
                "[yellow]⚠ AI chưa cấu hình (.env) → fallback sang chế độ heuristic[/yellow]"
            )
            providers = extract_heuristic(results)
        else:
            contexts = collect_page_contexts(results, max_pages=max_pages, timeout=timeout)
            console.print(
                f"[dim]Gửi {len(contexts)} trang + {len(results)} snippet cho AI trích xuất...[/dim]"
            )
            try:
                providers = extract_with_ai(contexts, results, keywords, cfg)
            except Exception as e:  # noqa: BLE001 — fallback heuristic thay vì crash
                console.print(f"[yellow]⚠ AI extraction lỗi, fallback heuristic: {e}[/yellow]")
                providers = extract_heuristic(results)
            # Gộp thêm candidate heuristic mà AI không bắt được (dedupe ở dưới lo phần trùng)
            providers = providers + extract_heuristic(results)
    else:
        providers = extract_heuristic(results)

    # Đảm bảo tag thống nhất cho heuristic providers
    for p in providers:
        if "web-discovered" not in p.tags:
            p.tags.append("web-discovered")
        if "deep-search" not in p.tags:
            p.tags.append("deep-search")

    return dedupe_providers(providers, existing=list(KNOWN_PROVIDERS))


def search_only(
    keywords: list[str],
    sources: list[str] | None = None,
    max_results: int = 10,
    timeout: float = 15.0,
) -> list[SearchResult]:
    """Chỉ search, không extract — hữu ích cho debug/test."""
    return run_search(keywords, sources, max_results, timeout)
