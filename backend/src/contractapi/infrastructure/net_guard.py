"""SSRF guard for outbound calls the server makes on a spec author's behalf (webhooks).

ponytail: resolves the host and checks every address right before sending. Ceiling: a
DNS answer could change between this check and the connect (rebinding window of
milliseconds); the upgrade path is connecting to the checked IP with an explicit Host/SNI.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib import request as urlrequest
from urllib.parse import urlsplit

from contractapi.core.config import get_settings


class BlockedDestination(Exception):  # reads as a reason in logs/DLQ
    pass


def assert_public_url(url: str) -> None:
    """Raise BlockedDestination unless the URL is http(s) to public internet addresses."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise BlockedDestination("only http(s) URLs with a host are allowed")
    if get_settings().webhook_allow_private:
        return
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BlockedDestination(f"cannot resolve host {parts.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise BlockedDestination(
                f"{parts.hostname} resolves to a private/internal address ({ip}); "
                "set WEBHOOK_ALLOW_PRIVATE=true only if you really mean to call internal services"
            )


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    """A redirect could point at an internal address after the check passed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise BlockedDestination(f"redirects are not followed (HTTP {code} → {newurl})")


def safe_opener() -> urlrequest.OpenerDirector:
    return urlrequest.build_opener(_NoRedirect)
