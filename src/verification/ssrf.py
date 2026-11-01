"""
SSRF guard nhẹ cho verify request — không thêm dependency.

Validate URL trước khi fetch (port logic từ app-free-llm-gateway ssrf-guard.ts):
- Chỉ cho phép scheme http/https
- Chặn hostname private (localhost, metadata.google.internal, *.localhost)
- Resolve DNS và chặn IP private/loopback/link-local/multicast/reserved
  (bao gồm 169.254.169.254 — metadata cloud, 127.0.0.0/8, 10/8, 172.16/12,
  192.168/16, 100.64/10 CGNAT, fc00::/7, fe80::/10, ::1 ...)
- Chặn URL chứa userinfo (http://user:pass@host)

Lưu ý: guard khử phần lớn rủi ro SSRF nhưng không chống đầy đủ DNS rebinding
(check-then-fetch có cửa sổ TOCTOU) — đủ cho use-case verify provider không nhạy cảm.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlparse


class SSRFBlockedError(Exception):
    """URL bị chặn bởi SSRF guard (scheme/hostname/IP không hợp lệ)."""


# Hostname hard-block không cần resolve
_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "instance-data"}

# Dải "không định tuyến public" mà ipaddress.is_private bỏ sót trên Python 3.13+
# (is_private mới chỉ theo IANA registry): CGNAT 100.64/10, benchmark 198.18/15,
# TEST-NET 192.0.2/24, 198.51.100/24, 203.0.113/24.
_EXTRA_BLOCKED_NETS = [
    ipaddress.ip_network(n)
    for n in (
        "100.64.0.0/10",
        "198.18.0.0/15",
        "192.0.2.0/24",
        "198.51.100.0/24",
        "203.0.113.0/24",
    )
]


def is_private_ip(ip_str: str) -> bool:
    """True nếu IP thuộc dải private/loopback/link-local/multicast/reserved."""
    try:
        addr = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False  # không phải IP — để tầng hostname xử lý
    # IPv4-mapped IPv6 (::ffff:127.0.0.1) → check IPv4 nhúng bên trong
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if any(addr in net for net in _EXTRA_BLOCKED_NETS):
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def resolve_hostname(hostname: str) -> list[str]:
    """
    Resolve hostname → list IP (mọi address family).

    Hàm riêng để test có thể monkeypatch (không cần network thật).
    Raise OSError khi DNS lookup thất bại.
    """
    return [str(info[4][0]) for info in socket.getaddrinfo(hostname, None)]


def _host_addresses(hostname: str, resolver: Callable[[str], list[str]]) -> list[str]:
    """Trả về list IP của hostname — hostname dạng IP literal thì trả luôn."""
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return resolver(hostname)
    return [hostname]


def validate_url(url: str, resolver: Callable[[str], list[str]] | None = None) -> str:
    """
    Validate URL trước khi fetch. Trả về URL nếu an toàn.

    Raises:
        SSRFBlockedError: scheme không http(s), hostname/IP private, userinfo, ...
    """
    if resolver is None:
        resolver = resolve_hostname

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise SSRFBlockedError(f"Blocked scheme: {parsed.scheme!r} (chỉ cho phép http/https)")
    if not parsed.hostname:
        raise SSRFBlockedError("URL thiếu hostname")
    if parsed.username or parsed.password:
        raise SSRFBlockedError("Blocked: URL chứa credentials (user:pass@host)")

    host = parsed.hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTNAMES or host.endswith(".localhost"):
        raise SSRFBlockedError(f"Blocked hostname: {host}")

    try:
        addrs = _host_addresses(host, resolver)
    except OSError as e:
        raise SSRFBlockedError(f"DNS lookup thất bại cho {host}: {e}") from e
    if not addrs:
        raise SSRFBlockedError(f"Hostname {host} không resolve được IP nào")

    for addr in addrs:
        if is_private_ip(addr):
            raise SSRFBlockedError(f"Blocked: {host} resolve tới IP private {addr}")

    return url
