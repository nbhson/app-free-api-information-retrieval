"""
Main CLI entry point
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from rich import box
from rich.console import Console
from rich.table import Table

from src.aggregation.aggregator import (
    aggregate_providers,
    save_to_json,
    save_to_yaml,
)
from src.config import get_ai_config
from src.discovery import KNOWN_PROVIDERS, get_provider_by_name, get_providers_by_tag
from src.discovery.ai_agent import AIDiscoveryError, discover_with_ai
from src.logging_config import get_logger, setup_logging
from src.models import ProviderStatus
from src.verification.checker import verify_all_providers, verify_provider

logger = get_logger("cli")

console = Console()


def _status_style(status: ProviderStatus) -> str:
    colors = {
        ProviderStatus.ACTIVE: "green",
        ProviderStatus.INACTIVE: "red",
        ProviderStatus.RATE_LIMITED: "yellow",
        ProviderStatus.UNKNOWN: "dim",
    }
    return colors.get(status, "dim")


def _print_provider_table(providers, show_all_models: bool = False) -> None:
    table = Table(box=box.ROUNDED, show_lines=False, title="Free LLM Providers")
    table.add_column("Provider", style="cyan", no_wrap=True)
    table.add_column("Status")
    table.add_column("Base URL", style="blue")
    table.add_column("Free Models", style="magenta")
    table.add_column("Auth", style="yellow")
    table.add_column("API Style", style="white")

    for p in providers:
        free_models = p.get_free_models()
        if not show_all_models:
            model_names = ", ".join(m.id for m in free_models[:3])
            if len(free_models) > 3:
                model_names += f" (+{len(free_models) - 3})"
        else:
            model_names = "\n".join(m.id for m in free_models)

        table.add_row(
            p.name,
            f"[{_status_style(p.status)}]{p.status.value}[/]",
            p.base_url,
            model_names or "-",
            "required" if p.auth_required else "none",
            p.api_style.value,
        )

    console.print(table)


@click.group()
def cli():
    """Free LLM Provider Discovery - Tìm và kiểm tra các LLM API miễn phí."""
    pass


@cli.command()
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    help="Định dạng đầu ra",
)
@click.option("--output", "-o", type=str, default=None, help="Đường dẫn file xuất dữ liệu")
@click.option("--verify", is_flag=True, default=False, help="Kiểm tra trạng thái endpoint")
@click.option("--show-all-models", is_flag=True, default=False, help="Hiển thị tất cả model")
@click.option(
    "--tag", "-t", multiple=True, help="Lọc theo tag (vd: --tag free-tier --tag openai-compatible)"
)
@click.option("--no-auth", is_flag=True, default=False, help="Chỉ hiện provider không cần API key")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Bật debug logging")
def list_cmd(fmt, output, verify, show_all_models, tag, no_auth, verbose):
    """Liệt kê tất cả provider đã biết."""
    if verbose:
        setup_logging("DEBUG")
    else:
        setup_logging("WARNING")  # mặc định quiet

    providers = list(KNOWN_PROVIDERS)

    # Lọc theo tag
    if tag:
        providers = [p for p in providers if any(t in p.tags for t in tag)]

    # Lọc chỉ hiện provider không cần auth
    if no_auth:
        providers = [p for p in providers if not p.auth_required]

    if verify:
        logger.info("Đang kiểm tra các endpoint...")
        providers = asyncio.run(verify_all_providers(providers))
        inactive = [p for p in providers if p.status == ProviderStatus.INACTIVE]
        if inactive:
            logger.warning("Có %d provider không hoạt động", len(inactive))
            sys.exit(1)

    # Lưu ra file trước (nếu có --output) để mọi định dạng đều nhận được dữ liệu
    if output:
        provider_list = aggregate_providers(providers)
        if output.endswith((".yaml", ".yml")):
            path = save_to_yaml(provider_list, output)
        else:
            path = save_to_json(provider_list, output)
        console.print(f"[green]✓[/green] Đã lưu vào [bold]{path}[/bold]")

    if fmt == "json":
        click.echo(
            json.dumps([p.model_dump(mode="json") for p in providers], indent=2, ensure_ascii=False)
        )
        return
    if fmt == "yaml":
        import yaml

        click.echo(
            yaml.dump(
                {"providers": [p.model_dump(mode="json") for p in providers]},
                allow_unicode=True,
                sort_keys=False,
            )
        )
        return

    _print_provider_table(providers, show_all_models=show_all_models)


@cli.command()
@click.option("--provider", "-p", required=True, help="Tên provider cần kiểm tra")
def check(provider):
    """Kiểm tra trạng thái của một provider."""
    p = get_provider_by_name(provider)
    if p is None:
        console.print(f"[red]✗[/red] Không tìm thấy provider '{provider}'.")
        console.print(
            f"[dim]Các provider khả dụng: {', '.join(x.name for x in KNOWN_PROVIDERS)}[/dim]"
        )
        sys.exit(1)

    console.print(f"[dim]Đang kiểm tra {p.name} ({p.base_url})...[/dim]")
    p = asyncio.run(verify_provider(p))

    if p.status == ProviderStatus.ACTIVE:
        console.print(f"[green]✓[/green] {p.name}: [green]ACTIVE[/green]")
        sys.exit(0)
    elif p.status == ProviderStatus.RATE_LIMITED:
        console.print(f"[yellow]⚠[/yellow] {p.name}: [yellow]RATE_LIMITED[/yellow]")
        sys.exit(2)
    else:
        console.print(f"[red]✗[/red] {p.name}: [{_status_style(p.status)}]{p.status.value}[/]")
        sys.exit(1)


@cli.command()
@click.option(
    "--output", "-o", type=str, default="data/providers.json", help="Đường dẫn file xuất dữ liệu"
)
def update(output):
    """Kiểm tra tất cả provider và cập nhật file dữ liệu."""
    logger.info("Đang kiểm tra tất cả provider...")
    providers = asyncio.run(verify_all_providers(list(KNOWN_PROVIDERS)))
    provider_list = aggregate_providers(providers)
    if output.endswith(".yaml") or output.endswith(".yml"):
        path = save_to_yaml(provider_list, output)
    else:
        path = save_to_json(provider_list, output)
    console.print(f"[green]✓[/green] Đã cập nhật và lưu vào [bold]{path}[/bold]")


@cli.command("discover-ai")
@click.option("--output", "-o", type=str, default=None, help="Lưu kết quả ra file JSON")
@click.option(
    "--verify", is_flag=True, default=False, help="Kiểm tra trạng thái các provider AI tìm thấy"
)
@click.option("--show", is_flag=True, default=True, help="Hiển thị kết quả ra màn hình")
def discover_ai(output, verify, show):
    """Dùng AI (.env config) để tìm kiếm provider miễn phí mới."""
    try:
        cfg = get_ai_config()
        console.print(f"[dim]Đang gọi AI ({cfg.model} @ {cfg.base_url})...[/dim]")
        found = discover_with_ai(cfg)
    except AIDiscoveryError as e:
        console.print(f"[red]✗ Lỗi AI discovery:[/red]\n{e}")
        sys.exit(1)

    console.print(f"\n[green]✓[/green] AI tìm thấy [bold]{len(found)}[/bold] provider:\n")

    # Deduplication với registry hiện tại — bỏ provider đã biết (trùng URL hoặc tên)
    if found:
        existing_urls = {p.base_url.lower() for p in KNOWN_PROVIDERS}
        existing_names = {p.name.lower() for p in KNOWN_PROVIDERS}
        original_count = len(found)
        found = [
            p
            for p in found
            if p.base_url.lower() not in existing_urls and p.name.lower() not in existing_names
        ]
        if original_count > len(found):
            console.print(
                f"[dim]Đã lọc {original_count - len(found)} provider trùng lặp với registry[/dim]"
            )

    if show and found:
        _print_provider_table(found, show_all_models=True)

    if verify and found:
        console.print("[dim]Đang kiểm tra các endpoint AI tìm thấy...[/dim]")
        found = asyncio.run(verify_all_providers(found))

    if output and found:
        provider_list = aggregate_providers(found)
        path = save_to_json(provider_list, output)
        console.print(f"[green]✓[/green] Đã lưu vào [bold]{path}[/bold]")

    # Lưu cả khi rỗng để người dùng biết
    if not found:
        console.print("[yellow]⚠ AI không trả về provider hợp lệ nào.[/yellow]")


@cli.command("health")
@click.option("--output", "-o", type=str, default=None, help="Lưu JSON ra file")
def health(output):
    """Kiểm tra nhanh sức khoẻ của hệ thống (registry + config)."""
    import json

    results = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "registry": {
            "total_providers": len(KNOWN_PROVIDERS),
            "free_tier_count": len(get_providers_by_tag("free-tier")),
            "verified_count": len(
                [p for p in KNOWN_PROVIDERS if p.status == ProviderStatus.ACTIVE]
            ),
        },
        "ai_configured": get_ai_config().is_configured(),
        "version": "1.1.0",
    }

    # Check xem có provider nào chưa verify không
    unknown_providers = [p for p in KNOWN_PROVIDERS if p.status == ProviderStatus.UNKNOWN]
    if unknown_providers:
        results["warnings"] = [f"{p.name} chưa được verify" for p in unknown_providers]

    if output:
        Path(output).write_text(json.dumps(results, indent=2, ensure_ascii=False))
        console.print(f"[green]✓[/green] Đã lưu health report vào [bold]{output}[/bold]")
    else:
        console.print("[bold]Health Check[/bold]")
        console.print(
            f"  Registry: {results['registry']['total_providers']} providers, "
            f"{results['registry']['free_tier_count']} free-tier, "
            f"{results['registry']['verified_count']} đã verify"
        )
        console.print(
            f"  AI Configured: "
            f"{'[green]✓[/green]' if results['ai_configured'] else '[yellow]⚠ Chưa cấu hình[/yellow]'}"
        )
        console.print(f"  Version: {results['version']}")
        if "warnings" in results:
            console.print(f"  [yellow]Warnings:[/yellow] {len(results['warnings'])}")
            for w in results["warnings"]:
                console.print(f"    • {w}")


def main():
    cli()


if __name__ == "__main__":
    main()
