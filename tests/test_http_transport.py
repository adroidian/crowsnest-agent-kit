"""M3/M2: the concrete _http_request() transport, exercised offline.

Uses an injected connection factory (the same call signature as
http.client.HTTPConnection) plus bounded fake responses -- no live
service, no loopback server needed. Covers connection failure,
timeout/error translation, HTTP status/body acquisition, the
response-size ceiling, bounded refusal diagnostics, and empty /
invalid-UTF-8 / non-JSON 2xx bodies.
"""
from __future__ import annotations

import http.client
import json
import socket

import pytest

from crowsnest_muse_worker.client import (
    MAX_ERROR_DETAIL_CHARS,
    MAX_RESPONSE_BYTES,
    CrowsnestHttpClient,
)
from crowsnest_muse_worker.errors import (
    ConfigurationError,
    ServiceRefusalError,
    TransportError,
    UncertainWriteError,
)


class FakeResponse:
    def __init__(self, status, body, read_exc=None):
        self.status = status
        self._body = body
        self._read_exc = read_exc
        self.read_sizes = []

    def read(self, amt=-1):
        self.read_sizes.append(amt)
        if self._read_exc is not None:
            raise self._read_exc
        if amt is None or amt < 0:
            return self._body
        return self._body[:amt]


class FakeConnection:
    def __init__(self, response=None, request_exc=None, response_exc=None):
        self._response = response
        self._request_exc = request_exc
        self._response_exc = response_exc
        self.requests = []
        self.closed = False

    def request(self, method, target, body=None, headers=None):
        self.requests.append((method, target, body, headers))
        if self._request_exc is not None:
            raise self._request_exc

    def getresponse(self):
        if self._response_exc is not None:
            raise self._response_exc
        return self._response

    def close(self):
        self.closed = True


def _factory_client(connection=None, factory_exc=None):
    """Client wired to the concrete _http_request via a fake factory."""
    calls = []

    def factory(host, port, timeout=None):
        calls.append((host, port, timeout))
        if factory_exc is not None:
            raise factory_exc
        return connection

    client = CrowsnestHttpClient(
        "http://127.0.0.1:8123/api", timeout=5, connection_factory=factory
    )
    return client, calls


# --- concrete transport: success / status+body acquisition ---------------

def test_http_request_acquires_status_and_body_and_closes():
    response = FakeResponse(200, b'{"gigs": []}')
    connection = FakeConnection(response=response)
    client, calls = _factory_client(connection)
    assert client.public_projection() == {"gigs": []}
    assert calls == [("127.0.0.1", 8123, 5.0)]
    (method, target, body, headers), = connection.requests
    assert method == "GET"
    assert target == "/api/v1/public/projection"
    assert body is None
    assert headers == {"Accept": "application/json"}
    # Bounded read was used (ceiling + 1), and the connection closed.
    assert response.read_sizes == [MAX_RESPONSE_BYTES + 1]
    assert connection.closed


def test_http_request_posts_signed_action_body():
    connection = FakeConnection(response=FakeResponse(200, b'{"state": "open"}'))
    client, _ = _factory_client(connection)
    envelope = {"body": {"action": "get_gig"}, "sig": "Zm9v"}
    assert client.signed_action("get_gig", envelope) == {"state": "open"}
    (method, target, body, headers), = connection.requests
    assert method == "POST"
    assert target == "/api/v1/actions/get_gig"
    assert json.loads(body.decode("utf-8")) == {"envelope": envelope}
    assert headers["Content-Type"] == "application/json"
    assert connection.closed


# --- concrete transport: failure translation ------------------------------

@pytest.mark.parametrize(
    "exc",
    [
        ConnectionRefusedError("refused"),
        ConnectionResetError("reset"),
        TimeoutError("timed out"),
        socket.timeout("timed out"),
        http.client.RemoteDisconnected("closed"),
        http.client.BadStatusLine("junk"),
        OSError("network unreachable"),
    ],
)
def test_http_request_translates_request_failures(exc):
    connection = FakeConnection(request_exc=exc)
    client, _ = _factory_client(connection)
    with pytest.raises(TransportError):
        client.public_projection()
    assert connection.closed


def test_http_request_translates_getresponse_failure():
    connection = FakeConnection(response_exc=http.client.HTTPException("x"))
    client, _ = _factory_client(connection)
    with pytest.raises(TransportError):
        client.public_projection()
    assert connection.closed


@pytest.mark.parametrize(
    "exc", [ConnectionRefusedError("refused"), TimeoutError("timed out")]
)
def test_http_request_translates_factory_connection_failure(exc):
    client, _ = _factory_client(factory_exc=exc)
    with pytest.raises(TransportError):
        client.public_projection()


def test_http_request_translates_factory_overflow_as_configuration():
    # Simulates a platform timeout-conversion failure raised while the
    # real connection class is being constructed.
    client, _ = _factory_client(factory_exc=OverflowError("out of range"))
    with pytest.raises(ConfigurationError):
        client.public_projection()


def test_http_request_enforces_response_size_ceiling():
    body = b'{"gigs": []}' + b" " * MAX_RESPONSE_BYTES
    connection = FakeConnection(response=FakeResponse(200, body))
    client, _ = _factory_client(connection)
    with pytest.raises(TransportError) as excinfo:
        client.public_projection()
    assert "exceeds" in str(excinfo.value)
    assert str(MAX_RESPONSE_BYTES) in str(excinfo.value)
    assert connection.closed


# --- P1-b: a received non-2xx status survives an unreadable body ---------
# Truncated, timeout and oversize bodies, each under a refusal status and
# under a 2xx status, through the concrete _http_request + write path.

_READ_FAILURES = [
    http.client.IncompleteRead(b"partial"),  # truncated body
    TimeoutError("timed out"),               # timeout during body read
    socket.timeout("timed out"),             # timeout (socket alias form)
]


@pytest.mark.parametrize("read_exc", _READ_FAILURES)
def test_unreadable_body_under_refusal_status_stays_refusal(read_exc):
    connection = FakeConnection(
        response=FakeResponse(409, b"", read_exc=read_exc))
    client, _ = _factory_client(connection)
    with pytest.raises(ServiceRefusalError) as excinfo:
        client.signed_write_action("brief_accept", {})
    assert excinfo.value.status == 409
    assert connection.closed


@pytest.mark.parametrize("read_exc", _READ_FAILURES)
def test_unreadable_body_under_2xx_is_uncertainty_not_refusal(read_exc):
    connection = FakeConnection(
        response=FakeResponse(200, b"", read_exc=read_exc))
    client, _ = _factory_client(connection)
    with pytest.raises(UncertainWriteError) as excinfo:
        client.signed_write_action("brief_accept", {})
    assert excinfo.value.action == "brief_accept"
    assert "UNKNOWN" in str(excinfo.value)
    assert connection.closed


@pytest.mark.parametrize("read_exc", _READ_FAILURES)
def test_unreadable_body_under_refusal_status_stays_refusal_on_read(read_exc):
    connection = FakeConnection(
        response=FakeResponse(503, b"", read_exc=read_exc))
    client, _ = _factory_client(connection)
    with pytest.raises(ServiceRefusalError) as excinfo:
        client.public_projection()
    assert excinfo.value.status == 503
    assert connection.closed


def test_oversize_body_under_refusal_status_stays_refusal():
    body = b'{"error": "x"}' + b" " * MAX_RESPONSE_BYTES
    connection = FakeConnection(response=FakeResponse(409, body))
    client, _ = _factory_client(connection)
    with pytest.raises(ServiceRefusalError) as excinfo:
        client.signed_write_action("brief_accept", {})
    assert excinfo.value.status == 409
    assert connection.closed


def test_oversize_body_under_2xx_is_uncertainty_not_refusal():
    body = b'{"ok": true}' + b" " * MAX_RESPONSE_BYTES
    connection = FakeConnection(response=FakeResponse(200, body))
    client, _ = _factory_client(connection)
    with pytest.raises(UncertainWriteError) as excinfo:
        client.signed_write_action("brief_accept", {})
    assert excinfo.value.action == "brief_accept"
    assert connection.closed


# --- I1 (quality): deeply nested JSON must not escape as RecursionError ---
# A ~4 KB body suffices to exhaust the JSON decoder's recursion limit;
# it is well below MAX_RESPONSE_BYTES, so it reaches the parsers.

NESTED_BODY = b'{"payload":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"


def test_deeply_nested_2xx_write_is_uncertainty_not_recursion_error():
    connection = FakeConnection(response=FakeResponse(200, NESTED_BODY))
    client, _ = _factory_client(connection)
    with pytest.raises(UncertainWriteError) as excinfo:
        client.signed_write_action("brief_accept", {})
    assert excinfo.value.action == "brief_accept"
    assert "UNKNOWN" in str(excinfo.value)
    assert "NOT retried" in str(excinfo.value)
    assert len(connection.requests) == 1  # exactly one dispatch, no retry
    assert connection.closed


def test_deeply_nested_non2xx_write_stays_refusal_with_native_status():
    connection = FakeConnection(response=FakeResponse(409, NESTED_BODY))
    client, _ = _factory_client(connection)
    with pytest.raises(ServiceRefusalError) as excinfo:
        client.signed_write_action("brief_accept", {})
    assert excinfo.value.status == 409  # known refusal/status preserved
    assert len(connection.requests) == 1
    assert connection.closed


def test_deeply_nested_2xx_read_is_transport_error_not_recursion_error():
    connection = FakeConnection(response=FakeResponse(200, NESTED_BODY))
    client, _ = _factory_client(connection)
    with pytest.raises(TransportError):
        client.public_projection()
    assert len(connection.requests) == 1
    assert connection.closed


# --- 2xx body interpretation (via the concrete-path client) ----------------

def _raw_client(handler):
    return CrowsnestHttpClient(
        "http://127.0.0.1:9/api", raw_request=lambda m, t, b: handler()
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"",                 # empty body
        b"\xff\xfe\xfd",     # invalid UTF-8
        b"not json",         # non-JSON
        b"[1, 2]",           # JSON list where an object is required
        b'"just a string"',  # JSON scalar where an object is required
    ],
)
def test_bad_2xx_bodies_are_transport_errors(raw):
    client = _raw_client(lambda: (200, raw))
    with pytest.raises(TransportError):
        client.public_projection()


def test_empty_2xx_is_not_a_success_for_signed_action():
    client = _raw_client(lambda: (204, b""))
    with pytest.raises(TransportError):
        client.signed_action("get_gig", {})


# --- M2: refusal diagnostics are bounded on every branch -------------------

def test_json_error_detail_is_truncated_to_common_limit():
    long_error = "x" * 1000
    body = json.dumps({"error": long_error}).encode("utf-8")
    client = _raw_client(lambda: (503, body))
    with pytest.raises(ServiceRefusalError) as excinfo:
        client.public_projection()
    assert excinfo.value.status == 503
    message = str(excinfo.value)
    assert "x" * MAX_ERROR_DETAIL_CHARS in message
    assert "x" * (MAX_ERROR_DETAIL_CHARS + 1) not in message
    # Prefix + bounded detail only; nowhere near the 1,000-char source.
    assert len(message) < 300


def test_plain_error_body_is_truncated_to_common_limit():
    client = _raw_client(lambda: (500, b"y" * 1000))
    with pytest.raises(ServiceRefusalError) as excinfo:
        client.public_projection()
    message = str(excinfo.value)
    assert "y" * MAX_ERROR_DETAIL_CHARS in message
    assert "y" * (MAX_ERROR_DETAIL_CHARS + 1) not in message


@pytest.mark.parametrize(
    "error_value",
    [{"detail": "nested"}, ["a", "list"], 12345, True],
)
def test_non_text_json_error_is_summarised_not_echoed(error_value):
    body = json.dumps({"error": error_value}).encode("utf-8")
    client = _raw_client(lambda: (403, body))
    with pytest.raises(ServiceRefusalError) as excinfo:
        client.public_projection()
    message = str(excinfo.value)
    assert "non-text error detail" in message
    assert "nested" not in message
