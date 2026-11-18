"""SSRF guard for outbound calls the server makes on a spec author's behalf (webhooks).

The host is resolved once, every address is checked, and the connection is opened to that
exact checked IP (Host header and TLS SNI/certificate still use the hostname). A DNS answer
that changes after the check (rebinding) cannot redirect the request to an internal address.
Redirects are never followed.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit

from contractapi.core.config import get_settings


class BlockedDestination(Exception):  # reads as a reason in logs/DLQ
    pass


def resolve_checked(url: str) -> tuple[str, str, int, str]:
    """Return (scheme, host, port, ip) for an allowed URL, else raise BlockedDestination."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise BlockedDestination("only http(s) URLs with a host are allowed")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BlockedDestination(f"cannot resolve host {parts.hostname}") from exc
    ips = [info[4][0] for info in infos]
    if not get_settings().webhook_allow_private:
        for raw in ips:
            ip = ipaddress.ip_address(raw)
            if not ip.is_global:
                raise BlockedDestination(
                    f"{parts.hostname} resolves to a private/internal address ({ip}); "
                    "set WEBHOOK_ALLOW_PRIVATE=true only if you really mean to call internal services"
                )
    return parts.scheme, parts.hostname, port, ips[0]


def assert_public_url(url: str) -> None:
    resolve_checked(url)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, *, pinned_ip: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, *, pinned_ip: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        # Certificate is verified against the hostname, not the IP.
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def post_checked(url: str, body: bytes, headers: dict[str, str], timeout: float) -> int:
    """POST to an allowed URL over a connection pinned to the checked IP; return the status."""
    scheme, host, port, ip = resolve_checked(url)
    parts = urlsplit(url)
    target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    cls = _PinnedHTTPSConnection if scheme == "https" else _PinnedHTTPConnection
    conn = cls(host, port, pinned_ip=ip, timeout=timeout)
    try:
        conn.request("POST", target, body=body, headers=headers)
        resp = conn.getresponse()
        resp.read()
    finally:
        conn.close()
    if 300 <= resp.status < 400:
        raise BlockedDestination(f"redirects are not followed (HTTP {resp.status})")
    return resp.status
