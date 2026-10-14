"""URL validation shared by discovery and direct retailer retrieval."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import ParseResult, urlparse


class UnsafeRetailerUrlError(ValueError):
    """Raised when a retailer URL is not safe for outbound retrieval."""


def _parse_http_url(value: str) -> ParseResult:
    try:
        parsed = urlparse(value.strip())
    except ValueError as exc:
        raise UnsafeRetailerUrlError("Retailer URL could not be parsed safely.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeRetailerUrlError("Retailer URL must be an HTTP(S) URL with a hostname.")
    if parsed.username or parsed.password:
        raise UnsafeRetailerUrlError("Retailer URL must not contain credentials.")
    return parsed


def _validate_ip_address(hostname: str) -> None:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise UnsafeRetailerUrlError("Retailer URL resolves to a non-public IP address.")


def validate_http_url(value: str, *, resolve_dns: bool = False) -> ParseResult:
    """Validate a public HTTP(S) URL, optionally checking all DNS answers."""

    parsed = _parse_http_url(value)
    hostname = parsed.hostname
    assert hostname is not None
    normalized = hostname.rstrip(".").lower()
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(".localhost"):
        raise UnsafeRetailerUrlError("Retailer URL must not target localhost.")
    _validate_ip_address(normalized)
    if resolve_dns:
        try:
            addresses = {
                ipaddress.ip_address(info[4][0])
                for info in socket.getaddrinfo(normalized, None, type=socket.SOCK_STREAM)
            }
        except (OSError, ValueError) as exc:
            raise UnsafeRetailerUrlError("Retailer hostname could not be resolved safely.") from exc
        if not addresses or any(not address.is_global for address in addresses):
            raise UnsafeRetailerUrlError("Retailer URL resolves to a non-public IP address.")
    return parsed


def safe_url(value: object) -> str | None:
    """Return a syntactically safe HTTP(S) URL for discovery, otherwise None."""

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        validate_http_url(value)
    except (UnsafeRetailerUrlError, ValueError):
        return None
    return value.strip()


def safe_hostname(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = validate_http_url(value)
    except (UnsafeRetailerUrlError, ValueError):
        try:
            parsed = urlparse(value)
        except ValueError:
            return None
    return parsed.hostname.lower() if parsed.hostname else None
