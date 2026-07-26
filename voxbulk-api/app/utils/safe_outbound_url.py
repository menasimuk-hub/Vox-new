"""Outbound URL safety helpers (SSRF / open-redirect hardening)."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
    }
)


def _hostname_is_private_or_local(hostname: str) -> bool:
    host = str(hostname or "").strip().lower().rstrip(".")
    if not host or host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return bool(
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        # Unresolvable host — reject to avoid DNS rebinding surprises on deliver.
        return True
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


def validate_public_https_callback_url(url: str | None, *, field_name: str = "callback_url") -> str:
    """Allow only https URLs to non-private hosts. Empty string is allowed (optional callback)."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https":
        raise ValueError(f"{field_name} must use https")
    if parsed.username or parsed.password:
        raise ValueError(f"{field_name} must not include credentials")
    host = parsed.hostname or ""
    if not host:
        raise ValueError(f"{field_name} host is required")
    if _hostname_is_private_or_local(host):
        raise ValueError(f"{field_name} must not target private or local addresses")
    return raw


def media_url_hostname(url: str) -> str | None:
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return None
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    return host or None


# Exact hosts / suffix allowlists for provider media downloads (no substring matching on full URL).
_META_MEDIA_HOSTS = frozenset(
    {
        "lookaside.fbsbx.com",
        "graph.facebook.com",
    }
)
_META_MEDIA_SUFFIXES = (".fbcdn.net", ".fbsbx.com", ".facebook.com")
_TELNYX_MEDIA_HOSTS = frozenset(
    {
        "api.telnyx.com",
        "media.telnyx.com",
        "s3.amazonaws.com",
    }
)
_TELNYX_MEDIA_SUFFIXES = (".telnyx.com", ".amazonaws.com")


def classify_media_download_host(hostname: str | None) -> str | None:
    """Return 'meta', 'telnyx', or None if host is not allowlisted for authenticated download."""
    host = str(hostname or "").strip().lower().rstrip(".")
    if not host:
        return None
    if host in _META_MEDIA_HOSTS or any(host.endswith(suf) for suf in _META_MEDIA_SUFFIXES):
        return "meta"
    if host in _TELNYX_MEDIA_HOSTS or any(host.endswith(suf) for suf in _TELNYX_MEDIA_SUFFIXES):
        return "telnyx"
    return None
