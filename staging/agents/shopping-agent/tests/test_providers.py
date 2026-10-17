from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shopping_agent import DiscoveryRequest, ProviderError
from shopping_agent import providers as provider_module


class _FakeResponse:
    def __init__(self, *, status=200, body=b"{}", headers=None):
        self.status = status
        self._body = body
        self._headers = headers or {"Content-Type": "application/json"}
        self.read_limits = []

    def getheaders(self):
        return list(self._headers.items())

    def read(self, amount=-1):
        self.read_limits.append(amount)
        return self._body if amount < 0 else self._body[:amount]


def test_serpapi_adapter_uses_google_shopping_and_secret_runtime_key(monkeypatch):
    observed = {}

    def request(url, timeout):
        observed["url"] = url
        observed["timeout"] = timeout
        payload = {
            "shopping_results": [
                {"title": "Garden hose", "link": "https://shop.example/hose"},
                {"title": "No link"},
                {"title": "Bad title", "link": None},
            ]
        }
        return json.dumps(payload).encode(), {"Content-Type": "application/json"}

    monkeypatch.setattr(provider_module, "_request_https", request)
    providers = provider_module.create_shopping_providers("secret-key", timeout_seconds=8)

    result = providers.google_shopping_search(
        DiscoveryRequest("garden hose", postcode="2000")
    )

    params = parse_qs(urlsplit(observed["url"]).query)
    assert urlsplit(observed["url"]).hostname == "serpapi.com"
    assert params["engine"] == ["google_shopping"]
    assert params["q"] == ["garden hose"]
    assert params["gl"] == ["au"]
    assert params["hl"] == ["en"]
    assert params["api_key"] == ["secret-key"]
    assert observed["timeout"] == 8
    assert result.value == [{"title": "Garden hose", "link": "https://shop.example/hose"}]
    assert result.usage.estimated_cost_usd is None


def test_missing_serpapi_key_disables_discovery():
    providers = provider_module.create_shopping_providers(None, timeout_seconds=5)
    assert providers.google_shopping_search is None
    assert providers.fetch_product_page is not None


def test_retailer_dns_private_addresses_are_rejected_before_connect(monkeypatch):
    def private_dns(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0], returncode=0, stdout="10.0.0.4 STREAM shop.example\n", stderr=""
        )

    monkeypatch.setattr(provider_module.subprocess, "run", private_dns)
    providers = provider_module.create_shopping_providers("key", timeout_seconds=5)

    with pytest.raises(ProviderError, match="retailer_dns_non_public"):
        providers.fetch_product_page("https://shop.example/product")


def test_retailer_connection_uses_the_validated_public_ip(monkeypatch):
    observed = {}

    def public_dns(command, **kwargs):
        observed["dns"] = (command, kwargs)
        return subprocess.CompletedProcess(
            command, returncode=0, stdout="93.184.216.34 STREAM shop.example\n", stderr=""
        )

    class FakeConnection:
        def __init__(self, host, address, *, timeout):
            observed["connection"] = (host, address, timeout)

        def request(self, method, path, *, headers):
            observed["request"] = (method, path, headers)

        def getresponse(self):
            return _FakeResponse(body=b"<html>ok</html>", headers={"Content-Type": "text/html"})

        def close(self):
            observed["closed"] = True

    monkeypatch.setattr(provider_module.subprocess, "run", public_dns)
    monkeypatch.setattr(provider_module, "_PinnedHTTPSConnection", FakeConnection)
    providers = provider_module.create_shopping_providers("key", timeout_seconds=7)

    result = providers.fetch_product_page("https://shop.example/products/hose?variant=2")

    assert observed["dns"][0] == ["getent", "ahosts", "shop.example"]
    assert observed["dns"][1]["timeout"] <= 7
    assert observed["connection"][0:2] == ("shop.example", "93.184.216.34")
    assert observed["connection"][2] > 0
    assert observed["request"][0:2] == ("GET", "/products/hose?variant=2")
    assert result.value["html"] == "<html>ok</html>"
    assert result.value["final_url"] == "https://shop.example/products/hose?variant=2"
    assert observed["closed"] is True


def test_retailer_redirects_are_rejected_and_never_followed(monkeypatch):
    class FakeConnection:
        def __init__(self, host, address, *, timeout):
            pass

        def request(self, method, path, *, headers):
            pass

        def getresponse(self):
            return _FakeResponse(status=302, headers={"Location": "http://127.0.0.1/admin"})

        def close(self):
            pass

    monkeypatch.setattr(provider_module, "_public_address", lambda *_: "93.184.216.34")
    monkeypatch.setattr(provider_module, "_PinnedHTTPSConnection", FakeConnection)
    providers = provider_module.create_shopping_providers("key", timeout_seconds=5)

    with pytest.raises(ProviderError, match="redirect_disallowed"):
        providers.fetch_product_page("https://shop.example/product")


def test_google_shopping_redirect_hosts_are_rejected_before_fetch(monkeypatch):
    monkeypatch.setattr(
        provider_module,
        "_request_https",
        lambda *_: pytest.fail("aggregator URL must not be fetched"),
    )
    providers = provider_module.create_shopping_providers("key", timeout_seconds=5)

    with pytest.raises(ProviderError, match="aggregator_url_rejected"):
        providers.fetch_product_page("https://www.google.co.uk/shopping/redirect")


def test_serpapi_error_body_is_not_exposed(monkeypatch):
    monkeypatch.setattr(
        provider_module,
        "_request_https",
        lambda *_: (b'{"error":"api_key=secret-key rejected"}', {"Content-Type": "application/json"}),
    )
    providers = provider_module.create_shopping_providers("secret-key", timeout_seconds=5)

    with pytest.raises(ProviderError) as error:
        providers.google_shopping_search(DiscoveryRequest("hose"))

    assert "secret-key" not in str(error.value)
    assert "api_key" not in str(error.value)


def test_https_rejects_oversize_content_length_without_reading_body(monkeypatch):
    monkeypatch.setattr(provider_module, "_MAX_RESPONSE_BYTES", 4)
    monkeypatch.setattr(provider_module, "_public_address", lambda *_: "93.184.216.34")
    response = _FakeResponse(
        body=b"not-read",
        headers={"Content-Type": "text/html", "Content-Length": "5"},
    )

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return response

        def close(self):
            pass

    monkeypatch.setattr(provider_module, "_PinnedHTTPSConnection", FakeConnection)

    with pytest.raises(ProviderError, match="response_too_large"):
        provider_module._request_https("https://shop.example/item", 1)

    assert response.read_limits == []


def test_https_bounds_body_without_content_length(monkeypatch):
    monkeypatch.setattr(provider_module, "_MAX_RESPONSE_BYTES", 4)
    monkeypatch.setattr(provider_module, "_public_address", lambda *_: "93.184.216.34")
    response = _FakeResponse(body=b"123456", headers={"Content-Type": "text/html"})

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return response

        def close(self):
            pass

    monkeypatch.setattr(provider_module, "_PinnedHTTPSConnection", FakeConnection)

    with pytest.raises(ProviderError, match="response_too_large"):
        provider_module._request_https("https://shop.example/item", 1)

    assert response.read_limits == [5]


def test_https_deadline_includes_slow_dns(monkeypatch):
    def slow_dns(command, *, timeout, **kwargs):
        time.sleep(timeout)
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(provider_module.subprocess, "run", slow_dns)
    started = time.monotonic()

    with pytest.raises(ProviderError, match="https_timeout"):
        provider_module._request_https("https://shop.example/item", 0.02)

    assert time.monotonic() - started < 0.3


def test_https_deadline_includes_slow_response(monkeypatch):
    monkeypatch.setattr(provider_module, "_public_address", lambda *_: "93.184.216.34")
    cancelled = threading.Event()
    worker_finished = threading.Event()

    class SlowResponse(_FakeResponse):
        def read(self, amount=-1):
            cancelled.wait(1)
            return super().read(amount)

    class FakeConnection:
        calls = 0

        def __init__(self, *args, **kwargs):
            FakeConnection.calls += 1

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            if FakeConnection.calls == 1:
                return SlowResponse(body=b"slow")
            return _FakeResponse(body=b"ok")

        def close(self):
            worker_finished.set()

        def cancel(self):
            cancelled.set()

    monkeypatch.setattr(provider_module, "_PinnedHTTPSConnection", FakeConnection)
    started = time.monotonic()

    with pytest.raises(ProviderError, match="https_timeout"):
        provider_module._request_https("https://shop.example/item", 0.02)

    assert time.monotonic() - started < 0.3
    assert worker_finished.wait(0.5)
    assert provider_module._request_https("https://shop.example/item", 1)[0] == b"ok"


def test_timeout_cancel_race_prevents_request_start(monkeypatch):
    monkeypatch.setattr(provider_module, "_public_address", lambda *_: "93.184.216.34")
    request_entered = threading.Event()
    allow_request_to_continue = threading.Event()
    worker_finished = threading.Event()
    sent = []

    class GatedConnection(provider_module._PinnedHTTPSConnection):
        def request(self, method, url, body=None, headers=None, *, encode_chunked=False):
            request_entered.set()
            allow_request_to_continue.wait(1)
            return super().request(method, url, body, headers, encode_chunked=encode_chunked)

        def cancel(self):
            super().cancel()
            allow_request_to_continue.set()

        def close(self):
            worker_finished.set()
            super().close()

    monkeypatch.setattr(provider_module, "_PinnedHTTPSConnection", GatedConnection)
    monkeypatch.setattr(
        provider_module.socket,
        "create_connection",
        lambda *args, **kwargs: sent.append("socket opened") or pytest.fail("cancelled request opened socket"),
    )

    with pytest.raises(ProviderError, match="https_timeout"):
        provider_module._request_https("https://shop.example/item", 0.02)

    request_entered.wait(0.5)
    assert worker_finished.wait(0.5)
    assert sent == []


def test_cancel_during_socket_creation_closes_socket_after_creation(monkeypatch):
    socket_creation_started = threading.Event()
    allow_socket_creation_to_finish = threading.Event()

    class FakeSocket:
        closed = False

        def close(self):
            self.closed = True

    raw_socket = FakeSocket()

    def delayed_create_connection(*args, **kwargs):
        socket_creation_started.set()
        allow_socket_creation_to_finish.wait(1)
        return raw_socket

    monkeypatch.setattr(provider_module.socket, "create_connection", delayed_create_connection)
    connection = provider_module._PinnedHTTPSConnection(
        "shop.example", "93.184.216.34", timeout=1
    )
    errors = []

    def connect():
        try:
            connection.connect()
        except OSError as exc:
            errors.append(exc)

    worker = threading.Thread(target=connect)
    worker.start()
    assert socket_creation_started.wait(0.5)
    connection.cancel()
    allow_socket_creation_to_finish.set()
    worker.join(0.5)

    assert not worker.is_alive()
    assert raw_socket.closed
    assert errors


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf")])
def test_provider_factory_rejects_non_finite_timeout(timeout):
    with pytest.raises(ValueError, match="finite"):
        provider_module.create_shopping_providers("key", timeout_seconds=timeout)
