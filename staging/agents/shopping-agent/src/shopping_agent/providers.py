"""Secret-from-environment SerpApi and safe direct retailer adapters.

Network requests use pinned public DNS answers, HTTPS only, and no redirects.
No browser automation or purchase capability is provided.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import math
import queue
import re
import socket
import ssl
import subprocess
import threading
import time
from collections.abc import Mapping
from urllib.parse import urlencode, urlsplit, urlunsplit

from .workflow import (
    DiscoveryRequest,
    ProviderCall,
    ProviderError,
    ProviderUsage,
    ShoppingProviders,
)

_SERPAPI_ENDPOINT = "https://serpapi.com/search"
_USER_AGENT = "ShoppingAgent/1.0 (product evidence fetcher)"
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_REQUEST_SLOTS = threading.BoundedSemaphore(8)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that dials a previously validated public IP."""

    def __init__(self, host: str, address: str, *, timeout: float) -> None:
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self._validated_address = address
        self._cancelled = threading.Event()
        self._socket_lock = threading.Lock()
        self._raw_socket: socket.socket | None = None

    def connect(self) -> None:
        if self._cancelled.is_set():
            raise OSError("request_cancelled")
        raw_socket = socket.create_connection(
            (self._validated_address, self.port),
            timeout=self.timeout,
            source_address=self.source_address,
        )
        with self._socket_lock:
            if self._cancelled.is_set():
                raw_socket.close()
                raise OSError("request_cancelled")
            self._raw_socket = raw_socket
        try:
            wrapped_socket = self._context.wrap_socket(raw_socket, server_hostname=self.host)
            with self._socket_lock:
                if self._cancelled.is_set():
                    wrapped_socket.close()
                    raise OSError("request_cancelled")
                self.sock = wrapped_socket
                self._raw_socket = None
        except Exception:
            raw_socket.close()
            raise

    def request(
        self,
        method: str,
        url: str,
        body=None,
        headers: Mapping[str, str] | None = None,
        *,
        encode_chunked: bool = False,
    ) -> None:
        if self._cancelled.is_set():
            raise OSError("request_cancelled")
        super().request(method, url, body, headers, encode_chunked=encode_chunked)

    def cancel(self) -> None:
        """Close a connection even while TCP/TLS setup is still in progress."""
        self._cancelled.set()
        with self._socket_lock:
            raw_socket = self._raw_socket
            active_socket = self.sock
            self._raw_socket = None
            self.sock = None
        if raw_socket is not None:
            raw_socket.close()
        if active_socket is not None:
            active_socket.close()


def _public_address(host: str, timeout_seconds: float) -> str:
    """Resolve once and return a public IP; reject mixed public/private answers."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        try:
            result = subprocess.run(
                ["getent", "ahosts", host],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError("https_timeout") from exc
        except OSError as exc:
            raise ProviderError("dns_resolver_unavailable") from exc
        if result.returncode != 0:
            raise ProviderError("retailer_dns_unavailable")
        addresses = list(dict.fromkeys(line.split()[0] for line in result.stdout.splitlines() if line.split()))
        if not addresses:
            raise ProviderError("retailer_dns_unavailable")
        try:
            parsed = [ipaddress.ip_address(item) for item in addresses]
        except ValueError as exc:
            raise ProviderError("retailer_dns_invalid") from exc
        if any(not item.is_global for item in parsed):
            raise ProviderError("retailer_dns_non_public")
        return addresses[0]
    if not address.is_global:
        raise ProviderError("retailer_ip_non_public")
    return host


def _request_https_worker(
    url: str,
    address: str,
    timeout_seconds: float,
    result_queue: queue.Queue,
    connection_state: dict,
    connection_lock: threading.Lock,
) -> None:
    """Perform a bounded request using only the caller's already validated address."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        connection = _PinnedHTTPSConnection(host, address, timeout=timeout_seconds)
        with connection_lock:
            cancelled = connection_state.get("cancelled", False)
            if not cancelled:
                connection_state["connection"] = connection
        if cancelled:
            connection.cancel()
            raise ProviderError("https_timeout")
        path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        connection.request("GET", path, headers={"User-Agent": _USER_AGENT, "Accept": "*/*"})
        response = connection.getresponse()
        if response.status in _REDIRECT_STATUSES:
            raise ProviderError("redirect_disallowed")
        if response.status < 200 or response.status >= 300:
            raise ProviderError("http_status")
        headers = dict(response.getheaders())
        content_length = next(
            (value for key, value in headers.items() if key.lower() == "content-length"),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) < 0 or int(content_length) > _MAX_RESPONSE_BYTES:
                    raise ProviderError("response_too_large")
            except ValueError as exc:
                raise ProviderError("invalid_content_length") from exc
        body = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise ProviderError("response_too_large")
        result_queue.put((body, headers, None))
    except ProviderError as exc:
        result_queue.put((None, None, exc))
    except (OSError, http.client.HTTPException, ssl.SSLError, ValueError) as exc:
        result_queue.put((None, None, ProviderError("https_request_failed")))
    except Exception:
        result_queue.put((None, None, ProviderError("https_request_failed")))
    finally:
        try:
            if "connection" in locals():
                connection.close()
        finally:
            _REQUEST_SLOTS.release()


def _request_https(url: str, timeout_seconds: float) -> tuple[bytes, Mapping[str, str]]:
    """GET HTTPS with a hard caller deadline, public-IP pinning, and bounded body."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ProviderError("invalid_timeout")
    if not _REQUEST_SLOTS.acquire(blocking=False):
        raise ProviderError("https_busy")
    worker_started = False
    try:
        deadline = time.monotonic() + timeout_seconds
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme.lower() != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
        ):
            raise ProviderError("https_url_rejected")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError("https_timeout")
        address = _public_address(host, remaining)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError("https_timeout")
        result_queue: queue.Queue = queue.Queue(maxsize=1)
        connection_state: dict = {}
        connection_lock = threading.Lock()
        worker = threading.Thread(
            target=_request_https_worker,
            args=(url, address, remaining, result_queue, connection_state, connection_lock),
            daemon=True,
            name="shopping-https-request",
        )
        worker.start()
        worker_started = True
        try:
            body, headers, error = result_queue.get(timeout=remaining)
        except queue.Empty as exc:
            with connection_lock:
                connection_state["cancelled"] = True
                connection = connection_state.get("connection")
            if connection is not None:
                try:
                    connection.cancel()
                except OSError:
                    pass
            raise ProviderError("https_timeout") from exc
        if error is not None:
            raise error
        return body, headers
    except Exception:
        raise
    finally:
        if not worker_started:
            _REQUEST_SLOTS.release()


def _serpapi_search(api_key: str, timeout_seconds: float, request: DiscoveryRequest) -> ProviderCall:
    if request.engine != "google_shopping":
        raise ProviderError("unsupported_search_engine")
    query = urlencode(
        {
            "engine": "google_shopping",
            "q": request.query,
            "gl": "au",
            "hl": "en",
            "api_key": api_key,
        }
    )
    body, _ = _request_https(f"{_SERPAPI_ENDPOINT}?{query}", timeout_seconds)
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError("serpapi_invalid_json") from exc
    if not isinstance(payload, Mapping) or payload.get("error"):
        raise ProviderError("serpapi_response_error")
    rows = payload.get("shopping_results")
    if not isinstance(rows, list):
        raise ProviderError("serpapi_results_unavailable")
    candidates = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        title = row.get("title")
        link = row.get("link") or row.get("product_link")
        if isinstance(title, str) and isinstance(link, str):
            candidates.append({"title": title, "link": link})
    return ProviderCall(candidates, usage=ProviderUsage())


def _retailer_fetch(timeout_seconds: float, url: str) -> ProviderCall:
    body, headers = _request_https(url, timeout_seconds)
    content_type = next((value for key, value in headers.items() if key.lower() == "content-type"), "")
    if "text/html" not in content_type.lower() and "application/xhtml+xml" not in content_type.lower():
        raise ProviderError("retailer_non_html_response")
    return ProviderCall(
        {"html": body.decode("utf-8", errors="replace"), "final_url": url},
        usage=ProviderUsage(),
    )


def create_shopping_providers(
    api_key: str | None,
    *,
    timeout_seconds: float,
) -> ShoppingProviders:
    """Create configured adapters; credentials are accepted only as runtime input."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be finite and greater than zero")
    if api_key is not None and (not api_key.strip() or re.search(r"\s", api_key)):
        raise ValueError("api_key must be a non-empty, whitespace-free value or None")
    key = api_key.strip() if api_key else None

    def fetch_page(url: str) -> ProviderCall:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
        if re.search(r"(^|[.])google[.][a-z.]+$", host) or re.search(
            r"(^|[.])googleusercontent[.]com$", host
        ):
            raise ProviderError("aggregator_url_rejected")
        return _retailer_fetch(timeout_seconds, url)

    search = (
        (lambda request: _serpapi_search(key, timeout_seconds, request))
        if key is not None
        else None
    )
    return ShoppingProviders(
        google_shopping_search=search,
        fetch_product_page=fetch_page,
    )
