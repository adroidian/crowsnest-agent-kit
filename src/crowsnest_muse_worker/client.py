"""HTTP transport for the finite Crowsnest read and worker-write surface.

Routes (measured from participant 0.3.2's CLI/lifecycle transport, which
documents them as read from the maintained service):

* ``GET  {base}/v1/public/projection``      -- public discovery
* ``POST {base}/v1/actions/{action}``       -- one signed action envelope

Only the read actions named in ``READ_ACTIONS`` can be dispatched through
:meth:`CrowsnestHttpClient.signed_action`; anything else raises before a
socket is opened. Exactly one request is issued per call: no redirects
are followed, nothing is retried and nothing is re-signed.

``my_gigs`` and ``artifact_history`` return native JSON lists (confirmed
in the lifecycle transport's ARRAY_RESULT_ACTIONS), so a 2xx list body is
a valid result for exactly those actions; other actions must return an
object.
"""
from __future__ import annotations

import http.client
import json
import urllib.parse
from typing import Any, Callable, Optional

from .config import validate_timeout_seconds
from .errors import (
    ConfigurationError,
    ServiceRefusalError,
    TransportError,
    UncertainWriteError,
)

# The complete read-only allowlist for this increment. Write actions
# (submit_proposal, brief_accept, consent_terms, attach/publish/deliver,
# ...) are deliberately absent and cannot be dispatched through here.
READ_ACTIONS = frozenset({"get_gig", "my_gigs", "artifact_history"})

# The finite worker write allowlist, mirrored from the 0.3.2 worker CLI
# (crowsnest_participant.worker ACTIONS): submit-proposal, brief-accept,
# consent-terms, attach-artifact, publish-artifact, deliver. Buyer actions
# (post_gig, select_proposal, review_artifact, accept_gig, ...), finance
# (issue_test_credit) and legacy claim_gig are deliberately absent and
# can never be dispatched as writes through this adapter.
WRITE_ACTIONS = frozenset({
    "submit_proposal", "brief_accept", "consent_terms",
    "attach_artifact", "publish_artifact", "deliver_gig",
})

# Actions whose accepted handler returns a native JSON list.
LIST_RESULT_ACTIONS = frozenset({"my_gigs", "artifact_history"})

RawRequest = Callable[[str, str, Optional[bytes]], tuple[int, bytes]]

# Connection factory signature compatible with http.client.HTTPConnection
# / HTTPSConnection: factory(host, port, timeout=...) -> connection.
ConnectionFactory = Callable[..., Any]

# One common ceiling for upstream error text surfaced as a diagnostic.
# Upstream bodies are UNTRUSTED: their text is truncated to this length
# on every branch (plain body and JSON ``error`` alike), non-text error
# values are summarised rather than echoed, and no claim is made that
# arbitrary upstream text could never resemble sensitive material.
MAX_ERROR_DETAIL_CHARS = 200

# Documented response-size ceiling: _http_request reads at most
# MAX_RESPONSE_BYTES + 1 bytes and refuses anything larger as a
# TransportError instead of buffering an unbounded body. 1 MiB is far
# above this read surface's JSON payloads (projection/gig/history).
MAX_RESPONSE_BYTES = 1_048_576


class CrowsnestHttpClient:
    """One-request-per-call HTTP client for the reads and worker writes above."""

    def __init__(self, base_url: str, *, timeout: float = 15.0,
                 raw_request: Optional[RawRequest] = None,
                 connection_factory: Optional[ConnectionFactory] = None) -> None:
        if not isinstance(base_url, str):
            raise ConfigurationError(
                "base URL must be an explicit http(s) URL"
            )
        # URL parsing/port access can raise ValueError (malformed IPv6,
        # non-numeric or out-of-range port). Translate precisely those
        # failures into a typed ConfigurationError and never echo the
        # supplied URL: it could contain credentials.
        try:
            parsed = urllib.parse.urlsplit(base_url.strip())
            scheme = parsed.scheme
            hostname = parsed.hostname
            port = parsed.port
            query = parsed.query
            fragment = parsed.fragment
            raw_path = parsed.path
        except ValueError:
            raise ConfigurationError(
                "base URL must be a valid http(s) URL"
            ) from None
        if scheme not in ("http", "https") or not hostname:
            raise ConfigurationError("base URL must be an explicit http(s) URL")
        if query or fragment:
            raise ConfigurationError("base URL must not carry a query or fragment")
        path = raw_path.rstrip("/")
        if path.endswith("/v1") or "/v1/actions" in path:
            raise ConfigurationError(
                "base URL must end at /api (or the origin); this client "
                "appends /v1/... itself"
            )
        if not path:
            path = "/api"
        self._scheme = scheme
        self._hostname = hostname
        self._port = port
        self._prefix = path
        self._timeout = validate_timeout_seconds(timeout, name="timeout")
        self._raw_request = raw_request or self._http_request
        self._connection_factory = connection_factory

    # -- public surface ---------------------------------------------------

    def public_projection(self) -> Any:
        """GET /v1/public/projection (the mounted discovery route)."""
        status, raw = self._raw_request(
            "GET", self._prefix + "/v1/public/projection", None
        )
        return self._interpret("projection", status, raw, expect_list=False)

    def signed_action(self, action: str, envelope: dict) -> Any:
        """POST one signed envelope to /v1/actions/{action} (reads only)."""
        if action not in READ_ACTIONS:
            raise TransportError(
                "%r is not in this adapter's read-only allowlist; "
                "refusing before any request" % (action,)
            )
        body = json.dumps({"envelope": envelope}).encode("utf-8")
        status, raw = self._raw_request(
            "POST", "%s/v1/actions/%s" % (self._prefix, action), body
        )
        return self._interpret(
            action, status, raw, expect_list=action in LIST_RESULT_ACTIONS
        )

    def signed_write_action(self, action: str, envelope: dict) -> Any:
        """POST one signed envelope for a worker write (writes only).

        Exactly one request is issued: nothing is retried and nothing
        is re-signed. A clear non-2xx answer stays a ServiceRefusalError
        (the service refused; that is knowledge). Any failure with no
        usable result after dispatch -- transport failure, empty or
        unparsable 2xx body -- becomes UncertainWriteError, because the
        write may already have committed.
        """
        if action not in WRITE_ACTIONS:
            raise TransportError(
                "%r is not in this adapter's worker-write allowlist; "
                "refusing before any request" % (action,)
            )
        body = json.dumps({"envelope": envelope}).encode("utf-8")
        try:
            status, raw = self._raw_request(
                "POST", "%s/v1/actions/%s" % (self._prefix, action), body
            )
            return self._interpret(action, status, raw, expect_list=False)
        except ServiceRefusalError:
            raise
        except TransportError as exc:
            raise UncertainWriteError(action, str(exc)) from exc

    # -- internals ----------------------------------------------------------

    def _http_request(self, method: str, target: str,
                      body: Optional[bytes]) -> tuple[int, bytes]:
        if self._connection_factory is not None:
            connector = self._connection_factory
        else:
            connector = (
                http.client.HTTPSConnection
                if self._scheme == "https"
                else http.client.HTTPConnection
            )
        try:
            connection = connector(self._hostname, self._port,
                                   timeout=self._timeout)
        except (OverflowError, ValueError) as exc:
            # e.g. a platform timeout-conversion failure at construction;
            # a configuration-class failure, with no URL echoed.
            raise ConfigurationError(
                "timeout must be a positive number the platform can "
                "represent"
            ) from exc
        except OSError as exc:
            raise TransportError(
                "%s %s: no usable response (%s)"
                % (method, target, type(exc).__name__)
            ) from exc
        try:
            headers = {"Accept": "application/json"}
            if body is not None:
                headers["Content-Type"] = "application/json"
            connection.request(method, target, body=body, headers=headers)
            response = connection.getresponse()
            status = response.status  # retained before the body is read
            # A response head was received: a non-2xx status is a known
            # service refusal even if the body then cannot be read
            # (truncated, timed out, oversize). Uncertainty is reserved
            # for an unusable 2xx or a missing response head.
            try:
                # Bounded read: one byte past the documented ceiling is
                # enough to refuse an oversize body without buffering it.
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            except (OSError, http.client.HTTPException) as exc:
                if not 200 <= status < 300:
                    raise ServiceRefusalError(
                        "%s %s: service returned HTTP %s "
                        "(body unreadable: %s)"
                        % (method, target, status, type(exc).__name__),
                        status=status,
                    ) from exc
                raise TransportError(
                    "%s %s: no usable response (%s)"
                    % (method, target, type(exc).__name__)
                ) from exc
            if len(raw) > MAX_RESPONSE_BYTES:
                if not 200 <= status < 300:
                    raise ServiceRefusalError(
                        "%s %s: service returned HTTP %s "
                        "(body exceeds the %d-byte ceiling)"
                        % (method, target, status, MAX_RESPONSE_BYTES),
                        status=status,
                    )
                raise TransportError(
                    "%s: response exceeds the %d-byte ceiling"
                    % (method, MAX_RESPONSE_BYTES)
                )
            return status, raw
        except (TransportError, ServiceRefusalError):
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise TransportError(
                "%s %s: no usable response (%s)"
                % (method, target, type(exc).__name__)
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _interpret(label: str, status: int, raw: bytes, *,
                   expect_list: bool) -> Any:
        if 200 <= status < 300:
            if not raw:
                raise TransportError("%s: empty body on HTTP %s" % (label, status))
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError, RecursionError) as exc:
                # RecursionError: deeply nested JSON (a few KB suffices)
                # exhausts the decoder's recursion limit, not ValueError.
                # Normalize narrowly here so an unusable 2xx stays a
                # TransportError (=> UncertainWriteError at the write
                # entrypoint), never a raw RecursionError.
                raise TransportError(
                    "%s: body on HTTP %s is not valid JSON" % (label, status)
                ) from exc
            if expect_list:
                if not isinstance(parsed, list):
                    raise TransportError(
                        "%s: result is %s, expected a JSON list"
                        % (label, type(parsed).__name__)
                    )
            elif not isinstance(parsed, dict):
                raise TransportError(
                    "%s: result is %s, expected a JSON object"
                    % (label, type(parsed).__name__)
                )
            return parsed
        # Upstream error text is untrusted. Extract it, summarise
        # non-text values instead of echoing them, then enforce ONE
        # common size limit on every branch (plain body and JSON).
        message = raw.decode("utf-8", "replace")
        try:
            parsed_error = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            # Deeply nested diagnostic JSON cannot be parsed (decoder
            # RecursionError); the already-known non-2xx head still
            # stands as a ServiceRefusalError with its native status,
            # falling back to the bounded plain-text message below.
            parsed_error = None
        if isinstance(parsed_error, dict) and parsed_error.get("error"):
            error_value = parsed_error["error"]
            if isinstance(error_value, str):
                message = error_value
            else:
                message = (
                    "service returned a non-text error detail (%s)"
                    % type(error_value).__name__
                )
        message = message[:MAX_ERROR_DETAIL_CHARS]
        raise ServiceRefusalError(
            "%s: service returned HTTP %s: %s" % (label, status, message),
            status=status,
        )
