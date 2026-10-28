"""Offline write-surface proof -- fake/recording transports only.

No live service is contacted. State names used in fixtures are fixture
values returned by the fake transport, not claimed service vocabulary:
the write service compares an optional caller-expected state against
whatever state the Task-1 terms read actually returns, and applies
structural prerequisites (brief/terms present, artifact known to
history, one-revision cap) read from those same Task-1 reads.
"""
from __future__ import annotations

import base64
import hashlib
import json

import pytest

from crowsnest_muse_worker.client import (
    MAX_JSON_NESTING_DEPTH,
    CrowsnestHttpClient,
)
from crowsnest_muse_worker.config import Settings
from crowsnest_muse_worker.errors import (
    InvalidInputError,
    InvalidReferenceError,
    ServiceRefusalError,
    TransportError,
    UncertainWriteError,
    WrongRoleError,
    WrongStateError,
)
from crowsnest_muse_worker.write_service import WorkWriteService

REF = "work_0123456789abcdef"
ART1 = "art_0000000000000001"
ART2 = "art_0000000000000002"
CONTENT = b"lantern task2 artifact bytes\n"
POLICY = {"on_review_silence": "accept", "on_dispute": "mediate"}
TERMS = {"budget_test_erg": "100", "eta": "2d"}


class FakeWriteClient:
    """Recording fake: reads via signed_action, writes via signed_write_action."""

    def __init__(self, *, terms=None, history=None, projection=None,
                 write_results=None, write_error=None, write_errors=None,
                 auto_update_history=True, history_sequence=None):
        self.calls = []  # ("read", action, envelope) / ("write", action, envelope)
        self._terms = {"work_ref": REF, "state": "fixture-state",
                       "brief": {"title": "demo"}, "agreed_terms": TERMS,
                       "resolution_policy": POLICY} if terms is None else terms
        self._history = [] if history is None else history
        self._projection = ({"gigs": [{"work_ref": REF}]}
                            if projection is None else projection)
        self._write_results = write_results or {}
        self._write_error = write_error
        self._write_errors = write_errors or {}
        self._auto_update_history = auto_update_history
        self._history_sequence = history_sequence
        self._history_reads = 0

    def public_projection(self):
        self.calls.append(("projection",))
        return self._projection

    def signed_action(self, action, envelope):
        self.calls.append(("read", action, envelope))
        if action == "get_gig":
            return self._terms
        if action == "artifact_history":
            if self._history_sequence is not None:
                idx = min(self._history_reads, len(self._history_sequence) - 1)
                self._history_reads += 1
                return list(self._history_sequence[idx])
            return list(self._history)
        return {}

    def signed_write_action(self, action, envelope):
        self.calls.append(("write", action, envelope))
        if self._write_error is not None:
            raise self._write_error
        if action in self._write_errors:
            raise self._write_errors[action]
        result = self._write_results.get(action, {})
        if action == "attach_artifact" and self._auto_update_history \
                and isinstance(result, dict) \
                and isinstance(result.get("artifact_id"), str) \
                and result["artifact_id"] not in {
                    e.get("artifact_id") for e in self._history
                    if isinstance(e, dict)}:
            # A real service records the newly issued id in history;
            # the happy-path fake must do the same (never-updating
            # history is the preflight-failure fixture, opted into
            # explicitly with auto_update_history=False).
            self._history = list(self._history) + [
                {"artifact_id": result["artifact_id"]}]
        return result

    def writes(self):
        return [c for c in self.calls if c[0] == "write"]


def _svc(actor_store, client, **kw):
    store, _ = actor_store
    settings = Settings(base_url="https://example.invalid/api",
                        store_path=store, account_id="acct-test-1")
    return WorkWriteService(settings, client, **kw)


# --- proposal -------------------------------------------------------------

def test_submit_proposal_maps_to_baseline_action(actor_store):
    client = FakeWriteClient()
    result = _svc(actor_store, client).submit_proposal(
        REF, scope="write a demo note", budget_test_erg=100, eta="2d")
    assert result == {}
    (kind, action, envelope), = client.writes()
    assert (kind, action) == ("write", "submit_proposal")
    body = envelope["body"]
    assert body["role"] == "worker" and body["account_id"] == "acct-test-1"
    assert body["params"] == {"work_ref": REF, "scope": "write a demo note",
                              "budget_test_erg": 100, "eta": "2d"}


def test_submit_proposal_refused_when_work_not_discovered(actor_store):
    client = FakeWriteClient(projection={"gigs": [{"work_ref": "work_ffffffffffffffff"}]})
    with pytest.raises(WrongStateError):
        _svc(actor_store, client).submit_proposal(REF, scope="s", budget_test_erg=1, eta="1d")
    assert client.writes() == []


def _live_projection(items):
    """Observed public-work-v1 structure; all values are offline fixtures."""
    return {
        "schema_version": "crowsnest-public-work-v1",
        "cash_value": False,
        "cashout_available": False,
        "counts": {"public_work": len(items) if isinstance(items, list) else 0},
        "credit_unit": "TEST ERG",
        "freshness": "current",
        "generated_at": "2026-10-27T00:00:00+00:00",
        "items": items,
    }


def _live_item(ref=REF):
    return {
        "id": ref,
        "title": "Offline fixture work",
        "description": "Synthetic adapter test, not a real commission.",
        "observed": {"as_of": "2026-10-27T00:00:00Z", "state": "posted"},
        "quote": {"amount": 300, "kind": "quote_not_payment", "unit": "TEST ERG"},
        "reported": "300",
        "artifact_url": None,
        "buyer": None,
        "worker": None,
        "verified": None,
    }


def test_submit_proposal_accepts_live_items_projection(actor_store):
    from crowsnest_muse_worker.service import WorkReadService

    projection = _live_projection([
        _live_item("work_ffffffffffffffff"), _live_item()])
    client = FakeWriteClient(projection=projection)
    # Discovery is already a passthrough; its returned id must also pass
    # the proposal preflight without rewriting the projection or reference.
    discovered = WorkReadService(Settings(), client).discover_work()
    assert discovered is projection
    client.calls.clear()
    result = _svc(actor_store, client).submit_proposal(
        discovered["items"][1]["id"], scope="write a demo note",
        budget_test_erg=300, eta="48h")
    assert result == {}
    (kind, action, envelope), = client.writes()
    assert (kind, action) == ("write", "submit_proposal")
    assert envelope["body"]["role"] == "worker"
    assert envelope["body"]["account_id"] == "acct-test-1"
    assert envelope["body"]["params"] == {
        "work_ref": REF, "scope": "write a demo note",
        "budget_test_erg": 300, "eta": "48h"}
    assert [c[0] for c in client.calls] == ["projection", "write"]


@pytest.mark.parametrize("items", [
    "not-a-list",
    {"id": REF},
    None,
    [],
    [REF],
    [{"title": "no id"}],
    [{"id": 42}],
    [{"work_ref": REF}],  # legacy entry key is not valid under items
    [_live_item("work_ffffffffffffffff")],
])
@pytest.mark.parametrize("legacy_present", [False, True])
def test_submit_proposal_live_items_fail_closed(
        actor_store, monkeypatch, items, legacy_present):
    import crowsnest_muse_worker.write_service as ws

    def unexpected_store_load(path):
        pytest.fail("rejected discovery must not load an actor store or sign")

    monkeypatch.setattr(ws, "load_actor_store", unexpected_store_load)
    projection = _live_projection(items)
    if legacy_present:
        # Present items is authoritative: malformed, empty or unmatched
        # items must never be rescued by a matching legacy entry.
        projection["gigs"] = [{"work_ref": REF}]
    client = FakeWriteClient(projection=projection)
    with pytest.raises(WrongStateError):
        _svc(actor_store, client).submit_proposal(
            REF, scope="s", budget_test_erg=300, eta="48h")
    assert client.writes() == []
    assert client.calls == [("projection",)]


def test_submit_proposal_matching_items_takes_precedence_over_gigs(actor_store):
    projection = _live_projection([_live_item()])
    projection["gigs"] = [{"work_ref": "work_ffffffffffffffff"}]
    client = FakeWriteClient(projection=projection)
    _svc(actor_store, client).submit_proposal(
        REF, scope="s", budget_test_erg=300, eta="48h")
    assert len(client.writes()) == 1
    assert [c[0] for c in client.calls] == ["projection", "write"]


@pytest.mark.parametrize("projection", [
    {},                                   # empty object: no gigs at all
    {"gigs": "not-a-list"},
    {"gigs": {"work_ref": REF}},          # gigs present but not a list
    {"other": [{"work_ref": REF}]},       # no gigs key
    [{"work_ref": REF}],                  # top-level list is not the container
    "not-an-object",
    42,
])
def test_submit_proposal_unrecognized_projection_fails_closed(actor_store, projection):
    client = FakeWriteClient()
    client._projection = projection
    with pytest.raises(WrongStateError):
        _svc(actor_store, client).submit_proposal(
            REF, scope="s", budget_test_erg=1, eta="1d")
    assert client.writes() == []
    assert [c[0] for c in client.calls] == ["projection"]  # read only, no write


def test_submit_proposal_none_projection_fails_closed(actor_store):
    client = FakeWriteClient()
    client._projection = None
    with pytest.raises(WrongStateError):
        _svc(actor_store, client).submit_proposal(
            REF, scope="s", budget_test_erg=1, eta="1d")
    assert client.writes() == []


@pytest.mark.parametrize("kwargs", [
    {"scope": "", "budget_test_erg": 1, "eta": "1d"},
    {"scope": "s", "budget_test_erg": 0, "eta": "1d"},
    {"scope": "s", "budget_test_erg": True, "eta": "1d"},
    {"scope": "s", "budget_test_erg": "100", "eta": "1d"},
    {"scope": "s", "budget_test_erg": 1, "eta": " "},
])
def test_submit_proposal_bad_input_refused_before_any_call(actor_store, kwargs):
    client = FakeWriteClient()
    with pytest.raises(InvalidInputError):
        _svc(actor_store, client).submit_proposal(REF, **kwargs)
    assert client.calls == []


def test_malformed_ref_refused_before_any_call(actor_store):
    client = FakeWriteClient()
    with pytest.raises(InvalidReferenceError):
        _svc(actor_store, client).submit_proposal("gig_1", scope="s", budget_test_erg=1, eta="1d")
    assert client.calls == []


def test_wrong_role_refused_before_any_call(actor_store):
    client = FakeWriteClient()
    with pytest.raises(WrongRoleError):
        _svc(actor_store, client, role="buyer").brief_accept(REF)
    assert client.calls == []


# --- brief / consent --------------------------------------------------------

def test_brief_accept_maps_and_carries_note(actor_store):
    client = FakeWriteClient()
    _svc(actor_store, client).brief_accept(REF, note="ok")
    (_, action, envelope), = client.writes()
    assert action == "brief_accept"
    assert envelope["body"]["params"] == {"work_ref": REF, "note": "ok"}


def test_brief_accept_wrong_expected_state_refused_before_write(actor_store):
    client = FakeWriteClient()  # fake state is "fixture-state"
    with pytest.raises(WrongStateError):
        _svc(actor_store, client).brief_accept(REF, expected_state="some-other-state")
    assert client.writes() == []
    assert [c[1] for c in client.calls] == ["get_gig"]  # only the Task-1 read


def test_brief_accept_without_brief_is_wrong_state(actor_store):
    client = FakeWriteClient(terms={"work_ref": REF, "state": "fixture-state"})
    with pytest.raises(WrongStateError):
        _svc(actor_store, client).brief_accept(REF)
    assert client.writes() == []


@pytest.mark.parametrize("bad_expected", ["", " ", 42, b"fixture-state", ["x"]])
def test_brief_accept_malformed_expected_state_before_anything(
        actor_store, monkeypatch, bad_expected):
    import crowsnest_muse_worker.write_service as ws

    store_loads = []
    monkeypatch.setattr(
        ws, "load_actor_store",
        lambda path: store_loads.append(path) or (_ for _ in ()).throw(
            AssertionError("store must not be loaded")))
    client = FakeWriteClient()
    with pytest.raises(InvalidInputError):
        _svc(actor_store, client).brief_accept(REF, expected_state=bad_expected)
    assert client.calls == []   # zero client calls of any kind
    assert store_loads == []    # zero actor-store loads (hence no signing)


@pytest.mark.parametrize("bad_expected", ["", " ", 42, b"fixture-state", ["x"]])
def test_deliver_work_malformed_expected_state_before_anything(
        actor_store, monkeypatch, bad_expected):
    import crowsnest_muse_worker.write_service as ws

    store_loads = []
    monkeypatch.setattr(
        ws, "load_actor_store",
        lambda path: store_loads.append(path) or (_ for _ in ()).throw(
            AssertionError("store must not be loaded")))
    client = FakeWriteClient(history=[{"artifact_id": ART1}])
    with pytest.raises(InvalidInputError):
        _svc(actor_store, client).deliver_work(
            REF, artifact_id=ART1, expected_state=bad_expected)
    assert client.calls == []
    assert store_loads == []


def test_consent_maps_with_exact_terms_and_complete_policy(actor_store):
    client = FakeWriteClient()
    _svc(actor_store, client).consent_terms(REF, agreed_terms=dict(TERMS),
                                            resolution_policy=dict(POLICY))
    (_, action, envelope), = client.writes()
    assert action == "consent_terms"
    assert envelope["body"]["params"] == {
        "work_ref": REF, "agreed_terms": TERMS, "resolution_policy": POLICY}


def test_consent_terms_mismatch_with_current_terms_refused(actor_store):
    client = FakeWriteClient()
    with pytest.raises(WrongStateError):
        _svc(actor_store, client).consent_terms(
            REF, agreed_terms={"budget_test_erg": "999"},
            resolution_policy=dict(POLICY))
    assert client.writes() == []


@pytest.mark.parametrize("policy", [
    None, {}, {"on_review_silence": "accept"},
    {"on_review_silence": "accept", "on_dispute": "mediate", "extra": "x"},
    {"on_review_silence": "", "on_dispute": "mediate"},
    {"on_review_silence": "accept", "on_dispute": 3},
])
def test_consent_partial_or_bad_policy_refused_before_any_call(actor_store, policy):
    client = FakeWriteClient()
    with pytest.raises(InvalidInputError):
        _svc(actor_store, client).consent_terms(REF, agreed_terms=dict(TERMS),
                                                resolution_policy=policy)
    assert client.calls == []


# --- artifact attach / publish / deliver ------------------------------------

def test_attach_binds_real_bytes_hash_and_size(actor_store):
    client = FakeWriteClient(write_results={"attach_artifact": {"artifact_id": ART1}})
    result = _svc(actor_store, client).attach_artifact(REF, media_type="text/plain", content=CONTENT)
    assert result == {"artifact_id": ART1}  # ID from transport, never invented
    (_, action, envelope), = client.writes()
    assert action == "attach_artifact"
    assert envelope["body"]["params"] == {
        "work_ref": REF, "media_type": "text/plain",
        "byte_size": len(CONTENT),
        "content_sha256": hashlib.sha256(CONTENT).hexdigest()}


def test_publish_sends_bytes_for_attached_id(actor_store):
    client = FakeWriteClient(history=[{"artifact_id": ART1}])
    _svc(actor_store, client).publish_artifact(REF, artifact_id=ART1, content=CONTENT)
    (_, action, envelope), = client.writes()
    assert action == "publish_artifact"
    params = envelope["body"]["params"]
    assert params["artifact_id"] == ART1 and params["work_ref"] == REF
    assert base64.b64decode(params["content_b64"]) == CONTENT


def test_publish_unknown_artifact_refused_before_write(actor_store):
    client = FakeWriteClient(history=[{"artifact_id": ART1}])
    with pytest.raises(WrongStateError):
        _svc(actor_store, client).publish_artifact(REF, artifact_id=ART2, content=CONTENT)
    assert client.writes() == []


def test_deliver_uses_supplied_service_id(actor_store):
    client = FakeWriteClient(history=[{"artifact_id": ART1}])
    _svc(actor_store, client).deliver_work(REF, artifact_id=ART1)
    (_, action, envelope), = client.writes()
    assert action == "deliver_gig"
    assert envelope["body"]["params"] == {"work_ref": REF, "artifact_id": ART1}


@pytest.mark.parametrize("bad_id", ["", "  ", None, 42])
def test_bad_artifact_id_refused_before_any_call(actor_store, bad_id):
    client = FakeWriteClient()
    with pytest.raises(InvalidInputError):
        _svc(actor_store, client).deliver_work(REF, artifact_id=bad_id)
    assert client.calls == []


def test_empty_content_refused_before_any_call(actor_store):
    client = FakeWriteClient()
    with pytest.raises(InvalidInputError):
        _svc(actor_store, client).attach_artifact(REF, media_type="text/plain", content=b"")
    assert client.calls == []


# --- revision: successor without overwriting, one-revision cap ---------------

def test_deliver_revision_attaches_publishes_delivers_new_id(actor_store):
    # The fake now records the newly issued id in history after attach
    # (as a real service would); per-step preflights re-read it.
    client = FakeWriteClient(
        history=[{"artifact_id": ART1}],
        write_results={"attach_artifact": {"artifact_id": ART2}})
    result = _svc(actor_store, client).deliver_revision(
        REF, media_type="text/plain", content=b"revised bytes")
    assert result["artifact_id"] == ART2
    assert [c[1] for c in client.writes()] == [
        "attach_artifact", "publish_artifact", "deliver_gig"]
    # A fresh terms+history preflight precedes EACH write step.
    sequence = [(c[0], c[1]) for c in client.calls]
    assert sequence == [
        ("read", "get_gig"), ("read", "artifact_history"),
        ("write", "attach_artifact"),
        ("read", "get_gig"), ("read", "artifact_history"),
        ("write", "publish_artifact"),
        ("read", "get_gig"), ("read", "artifact_history"),
        ("write", "deliver_gig"),
    ]
    publish_params = client.writes()[1][2]["body"]["params"]
    deliver_params = client.writes()[2][2]["body"]["params"]
    assert publish_params["artifact_id"] == ART2
    assert base64.b64decode(publish_params["content_b64"]) == b"revised bytes"
    assert deliver_params == {"work_ref": REF, "artifact_id": ART2}


def test_deliver_revision_cap_refused_before_write(actor_store):
    # Original + one revision already in history: cap reached.
    client = FakeWriteClient(history=[{"artifact_id": ART1}, {"artifact_id": ART2}])
    with pytest.raises(WrongStateError):
        _svc(actor_store, client).deliver_revision(REF, media_type="text/plain", content=b"x")
    assert client.writes() == []


def test_deliver_revision_without_prior_artifact_refused(actor_store):
    client = FakeWriteClient(history=[])
    with pytest.raises(WrongStateError):
        _svc(actor_store, client).deliver_revision(REF, media_type="text/plain", content=b"x")
    assert client.writes() == []


def test_deliver_revision_refuses_reused_service_id(actor_store):
    client = FakeWriteClient(
        history=[{"artifact_id": ART1}],
        write_results={"attach_artifact": {"artifact_id": ART1}})  # collision
    with pytest.raises(WrongStateError) as excinfo:
        _svc(actor_store, client).deliver_revision(REF, media_type="text/plain", content=b"x")
    assert [c[1] for c in client.writes()] == ["attach_artifact"]  # no publish/deliver
    # Known refusal, but completed attach + returned id are exposed.
    assert excinfo.value.completed_steps == ["attach_artifact"]
    assert excinfo.value.artifact_id == ART1
    assert "completed_steps=['attach_artifact']" in str(excinfo.value)
    assert "not atomic" in str(excinfo.value)


def test_deliver_revision_publish_preflight_requires_new_id_in_fresh_history(actor_store):
    # History NEVER updates after attach: the new id never appears.
    client = FakeWriteClient(
        history=[{"artifact_id": ART1}],
        write_results={"attach_artifact": {"artifact_id": ART2}},
        auto_update_history=False)
    with pytest.raises(WrongStateError) as excinfo:
        _svc(actor_store, client).deliver_revision(
            REF, media_type="text/plain", content=b"x")
    assert [c[1] for c in client.writes()] == ["attach_artifact"]  # zero publish dispatch
    assert excinfo.value.completed_steps == ["attach_artifact"]
    assert excinfo.value.artifact_id == ART2
    assert excinfo.value.revision_step == "publish_artifact"


def test_deliver_revision_deliver_preflight_requires_new_id_in_fresh_history(actor_store):
    # History contains the new id before publish, then no longer does.
    client = FakeWriteClient(
        history_sequence=[
            [{"artifact_id": ART1}],
            [{"artifact_id": ART1}, {"artifact_id": ART2}],
            [{"artifact_id": ART1}],
        ],
        write_results={"attach_artifact": {"artifact_id": ART2}})
    with pytest.raises(WrongStateError) as excinfo:
        _svc(actor_store, client).deliver_revision(
            REF, media_type="text/plain", content=b"x")
    assert [c[1] for c in client.writes()] == [
        "attach_artifact", "publish_artifact"]  # zero deliver dispatch
    assert excinfo.value.completed_steps == ["attach_artifact", "publish_artifact"]
    assert excinfo.value.artifact_id == ART2
    assert excinfo.value.revision_step == "deliver_gig"


def test_deliver_revision_attach_unusable_result_is_uncertainty(actor_store):
    client = FakeWriteClient(
        history=[{"artifact_id": ART1}],
        write_results={"attach_artifact": {}})  # no usable artifact_id
    with pytest.raises(UncertainWriteError) as excinfo:
        _svc(actor_store, client).deliver_revision(
            REF, media_type="text/plain", content=b"x")
    msg = str(excinfo.value)
    assert excinfo.value.action == "attach_artifact"
    assert "UNKNOWN" in msg and "NOT retried" in msg
    assert "inspect_terms" in msg and "inspect_history" in msg
    assert "publish_artifact and deliver_gig were NOT dispatched" in msg
    assert [c[1] for c in client.writes()] == ["attach_artifact"]


def test_deliver_revision_whitespace_attach_id_unchanged_history_is_uncertainty(
        actor_store):
    # Whitespace-only attach id, history unchanged afterwards: the
    # unusable result must end at attach as uncertainty, never be
    # reclassified as a later-step WrongStateError.
    client = FakeWriteClient(
        history=[{"artifact_id": ART1}],
        write_results={"attach_artifact": {"artifact_id": " "}},
        auto_update_history=False)
    with pytest.raises(UncertainWriteError) as excinfo:
        _svc(actor_store, client).deliver_revision(
            REF, media_type="text/plain", content=b"x")
    msg = str(excinfo.value)
    assert excinfo.value.action == "attach_artifact"
    assert "UNKNOWN" in msg and "NOT retried" in msg
    assert "NOT re-signed" in msg
    assert "inspect_terms" in msg and "inspect_history" in msg
    assert "publish_artifact and deliver_gig were NOT dispatched" in msg
    # Original token preserved verbatim as evidence, not stripped/repaired.
    assert excinfo.value.artifact_id == " "
    assert "' '" in msg
    assert excinfo.value.completed_steps == []
    assert excinfo.value.revision_step == "attach_artifact"
    assert [c[1] for c in client.writes()] == ["attach_artifact"]
    # Calls end at attach: zero publish/deliver dispatch (and no
    # post-attach preflight reads either).
    assert [(c[0], c[1]) for c in client.calls] == [
        ("read", "get_gig"), ("read", "artifact_history"),
        ("write", "attach_artifact")]


def test_deliver_revision_whitespace_attach_id_echoed_in_history_is_uncertainty(
        actor_store):
    # Whitespace-only attach id, and history echoes that exact value:
    # echoing must not make it usable -- still ends at attach as
    # uncertainty, with zero publish/deliver dispatch.
    client = FakeWriteClient(
        history=[{"artifact_id": ART1}],
        write_results={"attach_artifact": {"artifact_id": " "}},
        auto_update_history=True)  # fake records " " in history
    with pytest.raises(UncertainWriteError) as excinfo:
        _svc(actor_store, client).deliver_revision(
            REF, media_type="text/plain", content=b"x")
    msg = str(excinfo.value)
    assert excinfo.value.action == "attach_artifact"
    assert "UNKNOWN" in msg and "NOT retried" in msg
    assert "NOT re-signed" in msg
    assert "inspect_terms" in msg and "inspect_history" in msg
    assert "publish_artifact and deliver_gig were NOT dispatched" in msg
    assert excinfo.value.artifact_id == " "
    assert "' '" in msg
    assert excinfo.value.completed_steps == []
    assert excinfo.value.revision_step == "attach_artifact"
    assert [c[1] for c in client.writes()] == ["attach_artifact"]
    assert [(c[0], c[1]) for c in client.calls] == [
        ("read", "get_gig"), ("read", "artifact_history"),
        ("write", "attach_artifact")]


# Failure injection after EACH revision step: subsequent writes absent,
# known refusals stay known, uncertainties stay uncertain, and every
# error exposes the completed steps + returned id.
@pytest.mark.parametrize("failing,error,exc_type,expected_writes,completed", [
    ("attach_artifact", TransportError("boom"), UncertainWriteError,
     ["attach_artifact"], []),
    ("publish_artifact", ServiceRefusalError("refused", status=409),
     ServiceRefusalError, ["attach_artifact", "publish_artifact"],
     ["attach_artifact"]),
    ("publish_artifact", TransportError("boom"), UncertainWriteError,
     ["attach_artifact", "publish_artifact"], ["attach_artifact"]),
    ("deliver_gig", ServiceRefusalError("refused", status=403),
     ServiceRefusalError,
     ["attach_artifact", "publish_artifact", "deliver_gig"],
     ["attach_artifact", "publish_artifact"]),
    ("deliver_gig", TransportError("boom"), UncertainWriteError,
     ["attach_artifact", "publish_artifact", "deliver_gig"],
     ["attach_artifact", "publish_artifact"]),
])
def test_deliver_revision_failure_after_each_step(
        actor_store, failing, error, exc_type, expected_writes, completed):
    client = FakeWriteClient(
        history=[{"artifact_id": ART1}],
        write_results={"attach_artifact": {"artifact_id": ART2}},
        write_errors={failing: error})
    with pytest.raises(exc_type) as excinfo:
        _svc(actor_store, client).deliver_revision(
            REF, media_type="text/plain", content=b"x")
    assert [c[1] for c in client.writes()] == expected_writes
    if isinstance(error, ServiceRefusalError):
        assert excinfo.value.status == error.status  # known refusal stays known
        assert excinfo.value.artifact_id == ART2
    else:
        assert "UNKNOWN" in str(excinfo.value)
        # Uncertainty is named for the failing step (attach returns no
        # id yet, so only later steps can carry the returned id).
        if failing != "attach_artifact":
            assert excinfo.value.artifact_id == ART2
    assert excinfo.value.completed_steps == completed
    assert "do not restart blindly" in str(excinfo.value)


# --- I1/CI: deeply nested publish body after a successful attach ----------
# The publish step's response goes through the REAL CrowsnestHttpClient
# parsers (raw_request fake returning a deeply nested body), while
# reads/attach use the recording fake. Deterministic in ANY environment:
# the depth is 20x the client's explicit MAX_JSON_NESTING_DEPTH bound,
# enforced by its iterative scan before json.loads, so this does NOT
# rely on the decoder raising RecursionError at this depth (which
# varies by interpreter). The failure must surface as uncertainty (2xx)
# or a native-status refusal (409) -- never a raw RecursionError --
# with completed attach steps / new id preserved.

_NESTING = MAX_JSON_NESTING_DEPTH * 20
_NESTED_BODY = (
    b'{"payload":' + b"[" * _NESTING + b"0" + b"]" * _NESTING + b"}"
)


class _DepthPublishClient(FakeWriteClient):
    def __init__(self, *, publish_status, **kw):
        super().__init__(**kw)
        self.publish_dispatches = 0

        def raw(method, target, body):
            self.publish_dispatches += 1
            return (publish_status, _NESTED_BODY)

        self._http = CrowsnestHttpClient(
            "https://example.invalid/api", raw_request=raw)

    def signed_write_action(self, action, envelope):
        if action == "publish_artifact":
            self.calls.append(("write", action, envelope))
            return self._http.signed_write_action(action, envelope)
        return super().signed_write_action(action, envelope)


@pytest.mark.parametrize("publish_status,exc_type", [
    (200, UncertainWriteError),
    (409, ServiceRefusalError),
])
def test_deliver_revision_deeply_nested_publish_preserves_progress(
        actor_store, publish_status, exc_type):
    client = _DepthPublishClient(
        publish_status=publish_status,
        history=[{"artifact_id": ART1}],
        write_results={"attach_artifact": {"artifact_id": ART2}})
    with pytest.raises(exc_type) as excinfo:
        _svc(actor_store, client).deliver_revision(
            REF, media_type="text/plain", content=b"x")
    exc = excinfo.value
    assert [c[1] for c in client.writes()] == [
        "attach_artifact", "publish_artifact"]  # no deliver, no retry
    assert client.publish_dispatches == 1  # exactly one publish dispatch
    if publish_status == 409:
        assert exc.status == 409  # known refusal/status preserved
    else:
        assert "UNKNOWN" in str(exc) and "NOT retried" in str(exc)
    assert exc.completed_steps == ["attach_artifact"]
    assert exc.artifact_id == ART2
    assert exc.revision_step == "publish_artifact"
    assert "completed_steps=['attach_artifact']" in str(exc)
    assert "do not restart blindly" in str(exc)
    assert "inspect_terms" in str(exc) and "inspect_history" in str(exc)


# --- M1 (quality): malformed upstream IDs get bounded diagnostics ------------

def test_deliver_revision_huge_malformed_attach_id_diagnostic_is_bounded(
        actor_store):
    huge_id = {"unexpected": "X" * 100000}
    client = FakeWriteClient(
        history=[{"artifact_id": ART1}],
        write_results={"attach_artifact": {"artifact_id": huge_id}},
        auto_update_history=False)
    with pytest.raises(UncertainWriteError) as excinfo:
        _svc(actor_store, client).deliver_revision(
            REF, media_type="text/plain", content=b"x")
    exc = excinfo.value
    # Original token preserved unchanged on the exception for evidence.
    assert exc.artifact_id is huge_id
    # ...but its rendered diagnostic is bounded/summarized in both the
    # primary message and the progress note (no 100 KB echo).
    assert len(str(exc)) < 1000
    assert "X" * 200 not in str(exc)
    assert "truncated" in str(exc)
    assert [c[1] for c in client.writes()] == ["attach_artifact"]


def test_progress_annotator_bounds_huge_malformed_id_but_preserves_it():
    from crowsnest_muse_worker.errors import TransportError
    from crowsnest_muse_worker.write_service import WorkWriteService

    huge_id = {"unexpected": "X" * 100000}
    exc = TransportError("boom")
    WorkWriteService._annotate_revision_progress(
        exc, completed=["attach_artifact"], artifact_id=huge_id,
        step="publish_artifact")
    assert exc.artifact_id is huge_id
    assert exc.completed_steps == ["attach_artifact"]
    assert len(str(exc)) < 1000
    assert "X" * 200 not in str(exc)


# --- M2 (quality): progress defaults are not shared between errors ----------

def test_error_progress_defaults_are_instance_local():
    from crowsnest_muse_worker.errors import InvalidInputError

    first = InvalidInputError("one")
    second = InvalidInputError("two")
    assert first.completed_steps == [] and second.completed_steps == []
    assert first.completed_steps is not second.completed_steps
    first.completed_steps.append("attach_artifact")
    assert second.completed_steps == []
    assert InvalidInputError("three").completed_steps == []
    assert first.artifact_id is None and second.artifact_id is None
    assert first.revision_step is None


# --- uncertainty: never success, never retry ----------------------------------

def test_uncertain_write_is_typed_and_tells_caller_to_reconcile(actor_store):
    client = FakeWriteClient(write_error=TransportError("no usable response"))
    with pytest.raises(UncertainWriteError) as exc:
        _svc(actor_store, client).brief_accept(REF)
    msg = str(exc.value)
    assert "inspect_terms" in msg and "inspect_history" in msg
    assert "NOT retried" in msg
    assert len(client.writes()) == 1  # exactly one attempt, no auto-retry


def test_service_refusal_on_write_is_clear_not_uncertain(actor_store):
    client = FakeWriteClient(write_error=ServiceRefusalError("refused", status=403))
    with pytest.raises(ServiceRefusalError):
        _svc(actor_store, client).brief_accept(REF)


# --- HTTP client write dispatch ------------------------------------------------

def _http_client(handler):
    calls = []

    def raw(method, target, body):
        calls.append((method, target, body))
        return handler(method, target, body)

    return CrowsnestHttpClient("https://example.invalid/api", raw_request=raw), calls


def test_http_write_action_posts_to_named_route():
    client, calls = _http_client(lambda m, t, b: (200, b'{"artifact_id": "art_x"}'))
    envelope = {"body": {"action": "attach_artifact"}, "sig": "Zm9v"}
    assert client.signed_write_action("attach_artifact", envelope) == {"artifact_id": "art_x"}
    (method, target, body), = calls
    assert method == "POST" and target == "/api/v1/actions/attach_artifact"
    assert json.loads(body.decode()) == {"envelope": envelope}


def test_http_write_transport_failure_becomes_uncertainty():
    def boom(m, t, b):
        raise TransportError("no usable response (ConnectionError)")

    client, calls = _http_client(boom)
    with pytest.raises(UncertainWriteError):
        client.signed_write_action("brief_accept", {})
    assert len(calls) == 1


def test_http_write_unusable_2xx_becomes_uncertainty():
    client, _ = _http_client(lambda m, t, b: (200, b'not json'))
    with pytest.raises(UncertainWriteError):
        client.signed_write_action("brief_accept", {})


def test_http_write_non2xx_stays_clear_refusal():
    client, _ = _http_client(lambda m, t, b: (409, b'{"error": "wrong state"}'))
    with pytest.raises(ServiceRefusalError) as exc:
        client.signed_write_action("brief_accept", {})
    assert exc.value.status == 409


@pytest.mark.parametrize("action", ["get_gig", "my_gigs", "post_gig", "accept_gig",
                                    "issue_test_credit", "claim_gig", "nonsense"])
def test_http_write_entrypoint_refuses_non_worker_write_actions(action):
    client, calls = _http_client(lambda m, t, b: (200, b'{}'))
    with pytest.raises(TransportError):
        client.signed_write_action(action, {})
    assert calls == []


# --- MCP registry: exact full tool set ------------------------------------------

def test_mcp_tool_registry_exact_full_set():
    import asyncio

    from crowsnest_muse_worker.server import mcp

    tools = asyncio.run(mcp.list_tools())
    assert sorted(t.name for t in tools) == [
        "attach_artifact", "brief_accept", "consent_terms", "deliver_revision",
        "deliver_work", "discover_work", "inspect_history", "inspect_terms",
        "list_my_gigs", "publish_artifact", "submit_proposal",
    ]
