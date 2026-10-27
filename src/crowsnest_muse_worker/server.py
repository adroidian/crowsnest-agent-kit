"""Minimal stdio MCP server exposing Crowsnest worker tools.

Read tools (Task 1, read-only):

* ``discover_work``   -- public work discovery (GET /v1/public/projection)
* ``list_my_gigs``    -- the configured worker's own gigs (signed my_gigs)
* ``inspect_terms``   -- agreed terms / sanitized state by work_ref (get_gig)
* ``inspect_history`` -- artifact/review history by work_ref (artifact_history)

Write tools (Task 2, worker-only; each write is preceded by Task-1
pre-flight reads and refused locally on wrong state/role/input):

* ``submit_proposal`` -- propose on discovered public work
* ``brief_accept``    -- accept the brief for selected work
* ``consent_terms``   -- consent to the currently recorded terms
* ``attach_artifact`` -- attach real artifact bytes (hash/size descriptor)
* ``publish_artifact``-- publish bytes under a service-issued artifact_id
* ``deliver_work``    -- deliver a published artifact (deliver_gig)
* ``deliver_revision``-- attach+publish+deliver a successor version

Configuration comes from the environment only (see config.Settings):
``CROWSNEST_BASE_URL``, ``CROWSNEST_STORE``, ``CROWSNEST_ACCOUNT_ID``,
``CROWSNEST_TIMEOUT_SECONDS``. Tool input can never supply a store path,
an account id or a shell string; there is no shell anywhere in this
adapter. The service object is built lazily per call so that server
startup, ``initialize`` and ``tools/list`` succeed with no actor
configured -- only an actual signed read requires the store.
"""
from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .client import CrowsnestHttpClient
from .config import Settings
from .errors import CrowsnestError, InvalidInputError
from .service import WorkReadService
from .write_service import WorkWriteService

mcp = MCPServer(
    "crowsnest-muse-worker",
    version="0.1.0",
    instructions=(
        "Crowsnest worker surface: discover public work, list the "
        "configured worker's own gigs, inspect agreed terms and artifact "
        "history by public work_ref, and (worker-only) submit proposals, "
        "accept briefs, consent to recorded terms, attach/publish/deliver "
        "artifact bytes and deliver one successor revision. Writes are "
        "refused locally on wrong state or malformed input, and a write "
        "with an unknown outcome is reported as UncertainWriteError -- "
        "reconcile via inspect_terms/inspect_history, never assume."
    ),
)


def _service() -> WorkReadService:
    settings = Settings.from_env()
    client = CrowsnestHttpClient(
        settings.base_url, timeout=settings.timeout_seconds
    )
    return WorkReadService(settings, client)


def _write_service() -> WorkWriteService:
    settings = Settings.from_env()
    client = CrowsnestHttpClient(
        settings.base_url, timeout=settings.timeout_seconds
    )
    return WorkWriteService(settings, client)


def _decode_content(content_b64: str) -> bytes:
    """Decode tool-supplied artifact bytes; bad input refuses locally."""
    if not isinstance(content_b64, str) or not content_b64.strip():
        raise InvalidInputError("content_b64 is required (base64 of the artifact bytes)")
    try:
        data = base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidInputError("content_b64 is not valid base64") from exc
    if not data:
        raise InvalidInputError("content_b64 decodes to empty bytes")
    return data


def _call(fn, *args) -> Any:
    """Run one read or write, surfacing typed adapter errors as MCP tool errors.

    ``ToolError`` is the pinned SDK's anticipated-error mechanism: the
    client receives ``is_error=True`` with this message in content,
    instead of the generic ``Error executing tool <name>`` mask applied
    to unexpected exceptions. The message is ``<Category>: <detail>``
    (e.g. ``InvalidReferenceError: work_ref must be ...``); locally
    generated adapter messages contain no key material, and upstream
    diagnostic text is bounded/untrusted (see client.py).

    Callers pass a zero-argument lambda that constructs the service
    *inside* this wrapper, so ``ConfigurationError`` raised by
    ``_service()``/``Settings.from_env()`` during construction is
    converted too, not only errors from the service method itself.
    """
    try:
        return fn(*args)
    except CrowsnestError as exc:
        raise ToolError("%s: %s" % (type(exc).__name__, exc)) from exc


def _as_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, default=str)


@mcp.tool()
def discover_work() -> str:
    """Discover public work via GET /v1/public/projection (no actor needed)."""
    return _as_text(_call(lambda: _service().discover_work()))


@mcp.tool()
def list_my_gigs() -> str:
    """List the configured worker's own gigs (signed my_gigs read)."""
    return _as_text(_call(lambda: _service().list_my_gigs()))


@mcp.tool()
def inspect_terms(work_ref: str) -> str:
    """Inspect agreed terms and sanitized current state for a work_ref.

    work_ref must be 'work_' plus exactly 16 lowercase hex characters;
    malformed references fail locally before any signing or dispatch.
    """
    return _as_text(_call(lambda: _service().inspect_terms(work_ref)))


@mcp.tool()
def inspect_history(work_ref: str) -> str:
    """Inspect own artifact/review history for a work_ref."""
    return _as_text(_call(lambda: _service().inspect_history(work_ref)))


@mcp.tool()
def submit_proposal(work_ref: str, scope: str, budget_test_erg: int, eta: str) -> str:
    """Submit a proposal for discovered public work (worker-only).

    Refused locally if the work_ref is not in the discovered public
    projection, or any input is malformed.
    """
    return _as_text(_call(lambda: _write_service().submit_proposal(
        work_ref, scope=scope, budget_test_erg=budget_test_erg, eta=eta)))


@mcp.tool()
def brief_accept(work_ref: str, note: str = "", expected_state: str | None = None) -> str:
    """Accept the brief for this work (worker-only).

    Pre-flight reads current terms/state; refused before any write if
    no brief is recorded or the current state != expected_state.
    """
    return _as_text(_call(lambda: _write_service().brief_accept(
        work_ref, note=note, expected_state=expected_state)))


@mcp.tool()
def consent_terms(work_ref: str, agreed_terms: dict, resolution_policy: dict) -> str:
    """Consent to the terms currently recorded for this work (worker-only).

    agreed_terms must exactly match the recorded terms and
    resolution_policy must be complete; otherwise refused before any write.
    """
    return _as_text(_call(lambda: _write_service().consent_terms(
        work_ref, agreed_terms=agreed_terms, resolution_policy=resolution_policy)))


@mcp.tool()
def attach_artifact(work_ref: str, media_type: str, content_b64: str) -> str:
    """Attach artifact bytes (base64) for this work (worker-only).

    Sends the byte count and SHA-256 of the actual bytes; returns the
    service-issued artifact_id to use for publish/deliver.
    """
    return _as_text(_call(lambda: _write_service().attach_artifact(
        work_ref, media_type=media_type, content=_decode_content(content_b64))))


@mcp.tool()
def publish_artifact(work_ref: str, artifact_id: str, content_b64: str,
                     media_type: str = "") -> str:
    """Publish artifact bytes under a service-issued artifact_id (worker-only).

    Refused before any write if artifact_id is not in this work's history.
    """
    return _as_text(_call(lambda: _write_service().publish_artifact(
        work_ref, artifact_id=artifact_id, content=_decode_content(content_b64),
        media_type=media_type or None)))


@mcp.tool()
def deliver_work(work_ref: str, artifact_id: str,
                 expected_state: str | None = None) -> str:
    """Deliver a published artifact for this work (worker-only, deliver_gig)."""
    return _as_text(_call(lambda: _write_service().deliver_work(
        work_ref, artifact_id=artifact_id, expected_state=expected_state)))


@mcp.tool()
def deliver_revision(work_ref: str, media_type: str, content_b64: str) -> str:
    """Deliver a successor version of the artifact (worker-only).

    Attaches a NEW service-issued artifact_id, publishes the new bytes
    under it and delivers it; the prior version is never overwritten.
    Refused before any write once the one-revision cap is reached.
    """
    return _as_text(_call(lambda: _write_service().deliver_revision(
        work_ref, media_type=media_type, content=_decode_content(content_b64))))


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
