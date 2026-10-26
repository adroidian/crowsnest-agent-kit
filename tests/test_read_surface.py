"""Offline/protocol proof only -- no live Crowsnest service is contacted.

These tests use fixture keystores and recording/fake transports. They
prove validation, envelope signing, routing-to-URL mapping, allowlist
enforcement and the MCP tool registry shape. They are NOT live service
proof.
"""
from __future__ import annotations

import base64
import json

import pytest
from nacl.signing import VerifyKey

from crowsnest_muse_worker.client import CrowsnestHttpClient
from crowsnest_muse_worker.config import Settings
from crowsnest_muse_worker.errors import (
    ActorStoreError,
    ConfigurationError,
    InvalidReferenceError,
    ServiceRefusalError,
    TransportError,
)
from crowsnest_muse_worker.identity import load_actor_store
from crowsnest_muse_worker.service import WorkReadService
from crowsnest_muse_worker.validation import require_work_ref

VALID_REF = "work_0123456789abcdef"


# --- validation: invalid references fail before store load / dispatch -----

@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        123,
        "gig_0123456789abcdef",        # private-selector shape: not accepted
        "work_0123456789abcde",        # too short
        "work_0123456789abcdef0",      # too long
        "work_0123456789ABCDEF",       # uppercase hex
        "work_0123456789abcdeg",       # non-hex
        "work_0123456789abcdef/extra", # path smuggling attempt
        "../work_0123456789abcdef",
    ],
)
def test_require_work_ref_rejects_malformed(bad):
    with pytest.raises(InvalidReferenceError):
        require_work_ref(bad)


def test_require_work_ref_accepts_service_shape():
    assert require_work_ref(VALID_REF) == VALID_REF


# --- service: mapping, validation order, configured actor binding ---------

def _settings(store=None, account="acct-test-1"):
    return Settings(base_url="https://example.invalid/api",
                    store_path=store, account_id=account)


def test_inspect_terms_dispatches_get_gig_with_work_ref_only(
        actor_store, recording_client):
    store, principal_id = actor_store
    service = WorkReadService(_settings(store), recording_client)
    result = service.inspect_terms(VALID_REF)
    assert result == {}
    (kind, action, envelope), = recording_client.calls
    assert kind == "signed" and action == "get_gig"
    body = envelope["body"]
    assert body["action"] == "get_gig"
    assert body["params"] == {"work_ref": VALID_REF}
    assert body["role"] == "worker"
    assert body["account_id"] == "acct-test-1"
    assert body["principal_id"] == principal_id
    # The envelope signature must verify against the fixture public key.
    identity = load_actor_store(store)
    verify_key = VerifyKey(base64.b64decode(identity.public_key_b64))
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode("utf-8")
    verify_key.verify(canonical, base64.b64decode(envelope["sig"]))


def test_inspect_history_dispatches_artifact_history(
        actor_store, recording_client):
    store, _ = actor_store
    service = WorkReadService(_settings(store), recording_client)
    service.inspect_history(VALID_REF)
    (_, action, envelope), = recording_client.calls
    assert action == "artifact_history"
    assert envelope["body"]["params"] == {"work_ref": VALID_REF}


def test_list_my_gigs_dispatches_my_gigs(actor_store, recording_client):
    store, _ = actor_store
    service = WorkReadService(_settings(store), recording_client)
    service.list_my_gigs()
    (_, action, envelope), = recording_client.calls
    assert action == "my_gigs"
    assert envelope["body"]["params"] == {}


def test_discover_work_uses_public_projection(recording_client):
    service = WorkReadService(_settings(store=None), recording_client)
    assert service.discover_work() == {"gigs": []}
    assert recording_client.calls == [("projection",)]


def test_invalid_ref_fails_before_store_load_and_dispatch(recording_client):
    # Store deliberately unconfigured: validation must fire first, so the
    # caller gets InvalidReferenceError, not ConfigurationError, and the
    # client is never touched.
    service = WorkReadService(_settings(store=None), recording_client)
    with pytest.raises(InvalidReferenceError):
        service.inspect_terms("work_nope")
    assert recording_client.calls == []


def test_signed_read_without_configured_actor_fails_typed(
        actor_store, recording_client):
    store, _ = actor_store
    service = WorkReadService(_settings(store=store, account=None),
                              recording_client)
    with pytest.raises(ConfigurationError):
        service.list_my_gigs()
    assert recording_client.calls == []


def test_signed_read_with_missing_store_fails_typed(recording_client, tmp_path):
    service = WorkReadService(
        _settings(store=str(tmp_path / "absent.json")), recording_client)
    with pytest.raises(ActorStoreError):
        service.list_my_gigs()
    assert recording_client.calls == []


def test_fresh_nonce_per_envelope(actor_store, recording_client):
    store, _ = actor_store
    service = WorkReadService(_settings(store), recording_client)
    service.list_my_gigs()
    service.list_my_gigs()
    nonces = [call[2]["body"]["nonce"] for call in recording_client.calls]
    assert nonces[0] != nonces[1]


# --- identity store consistency ---------------------------------------------

def test_inconsistent_store_rejected(tmp_path, actor_store):
    store, _ = actor_store
    payload = json.loads(open(store).read())
    payload["principal_id"] = "p_" + "0" * 24
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ActorStoreError):
        load_actor_store(str(bad_path))


# --- HTTP client: wire mapping, allowlist, result shapes (fake raw layer) --

def _client(handler):
    calls = []

    def raw(method, target, body):
        calls.append((method, target, body))
        return handler(method, target, body)

    client = CrowsnestHttpClient("https://example.invalid/api", raw_request=raw)
    return client, calls


def test_projection_maps_to_mounted_get_route():
    client, calls = _client(lambda m, t, b: (200, b'{"gigs": []}'))
    assert client.public_projection() == {"gigs": []}
    (method, target, body), = calls
    assert method == "GET"
    assert target == "/api/v1/public/projection"
    assert body is None


def test_signed_action_posts_envelope_to_action_route():
    client, calls = _client(lambda m, t, b: (200, b'{"state": "open"}'))
    envelope = {"body": {"action": "get_gig"}, "sig": "Zm9v"}
    assert client.signed_action("get_gig", envelope) == {"state": "open"}
    (method, target, body), = calls
    assert method == "POST"
    assert target == "/api/v1/actions/get_gig"
    assert json.loads(body.decode("utf-8")) == {"envelope": envelope}


def test_list_actions_accept_json_list_results():
    client, _ = _client(lambda m, t, b: (200, b'[{"work_ref": "x"}]'))
    assert client.signed_action("artifact_history", {}) == [{"work_ref": "x"}]
    client2, _ = _client(lambda m, t, b: (200, b'[]'))
    assert client2.signed_action("my_gigs", {}) == []


def test_wrong_shape_2xx_is_transport_error_not_success():
    client, _ = _client(lambda m, t, b: (200, b'["not", "an", "object"]'))
    with pytest.raises(TransportError):
        client.signed_action("get_gig", {})


def test_non_2xx_keeps_native_status():
    client, _ = _client(lambda m, t, b: (403, b'{"error": "refused"}'))
    with pytest.raises(ServiceRefusalError) as excinfo:
        client.public_projection()
    assert excinfo.value.status == 403


@pytest.mark.parametrize("action", [
    "post_gig", "submit_proposal", "brief_accept", "consent_terms",
    "attach_artifact", "publish_artifact", "deliver_gig", "accept_gig",
    "claim_gig", "issue_test_credit",
])
def test_write_and_unknown_actions_refused_before_request(action):
    def handler(m, t, b):  # must never run
        raise AssertionError("request attempted for refused action")

    client, calls = _client(handler)
    with pytest.raises(TransportError):
        client.signed_action(action, {})
    assert calls == []


# --- MCP tool registry: read tools present (exact full set is proven
# in test_write_surface.py now that Task 2 added the worker write tools)

def test_mcp_tool_registry_includes_read_tools():
    import asyncio

    from crowsnest_muse_worker.server import mcp

    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}
    assert {
        "discover_work",
        "inspect_history",
        "inspect_terms",
        "list_my_gigs",
    } <= names


def test_settings_reject_bad_timeout():
    with pytest.raises(ConfigurationError):
        Settings.from_env({"CROWSNEST_TIMEOUT_SECONDS": "nope"})
