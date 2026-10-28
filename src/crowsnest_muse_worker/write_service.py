"""Write half of the worker lifecycle: offline-proven mappings only.

Mapping to participant 0.3.2's worker CLI (``crowsnest-worker``), whose
fixed action per subcommand is mirrored here (inspect-only baseline;
nothing vendored):

* ``submit_proposal`` -> action ``submit_proposal`` (submit-proposal)
* ``brief_accept``    -> action ``brief_accept`` (brief-accept)
* ``consent_terms``   -> action ``consent_terms`` (consent-terms)
* ``attach_artifact`` -> action ``attach_artifact`` (attach-artifact)
* ``publish_artifact``-> action ``publish_artifact`` (publish-artifact)
* ``deliver_work``    -> action ``deliver_gig`` (deliver)
* ``deliver_revision``-> attach + publish + deliver with a NEW service-
  issued artifact id (successor version; never an overwrite)

Guard discipline, in order, for every write:

1. Local input validation (work_ref shape, non-empty scope/ids/bytes,
   complete resolution policy, positive non-bool budget) and the
   worker-role check run BEFORE the actor store is loaded, before
   anything is signed and before any client call at all.
2. A pre-flight Task-1 read (public projection, ``get_gig`` terms/state
   or ``artifact_history``) establishes current state. Structural
   prerequisites and an optional caller-expected state are checked
   against what that read actually returned; on mismatch the write is
   refused with WrongStateError and the write action is never sent.
   This adapter invents no service state names.
3. Exactly one signed write dispatch per step. A transport failure
   after dispatch becomes UncertainWriteError (never success, never
   auto-retry); a clear non-2xx stays ServiceRefusalError.

Tool input can never override the actor store, account or role: all
three are bound from configuration here, exactly as in the read side.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Any, Protocol

from .config import WORKER_ROLE, Settings
from .errors import (
    CrowsnestError,
    InvalidInputError,
    ServiceRefusalError,
    TransportError,
    UncertainWriteError,
    WrongRoleError,
    WrongStateError,
)
from .identity import load_actor_store
from .validation import require_work_ref

# The canonical resolution-policy keys, from the 0.3.2 worker CLI: a
# partial policy would be silently completed with service defaults and
# written as the contract term, so completeness is refused locally.
POLICY_KEYS = ("on_review_silence", "on_dispute")

# One-revision cap: original delivery plus at most one successor.
MAX_ARTIFACT_VERSIONS = 2

# Bound for the diagnostic rendering of a (possibly malformed) upstream
# artifact_id in error messages. The original value is preserved
# unchanged on the exception's ``artifact_id`` attribute for evidence;
# only its text rendering here is summarized, so a huge structured
# value cannot expand an error message without limit.
MAX_ARTIFACT_ID_DIAGNOSTIC_CHARS = 80


def _bounded_id_diagnostic(value: object) -> str:
    """Bounded repr of an upstream id token for error diagnostics."""
    text = repr(value)
    if len(text) <= MAX_ARTIFACT_ID_DIAGNOSTIC_CHARS:
        return text
    return "%s... [truncated: %d chars total, type %s]" % (
        text[:MAX_ARTIFACT_ID_DIAGNOSTIC_CHARS],
        len(text),
        type(value).__name__,
    )


class WriteClient(Protocol):
    def public_projection(self) -> Any: ...

    def signed_action(self, action: str, envelope: dict) -> Any: ...

    def signed_write_action(self, action: str, envelope: dict) -> Any: ...


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError("%s is required and must be a non-empty string" % name)
    return value


def _require_bytes(value: object) -> bytes:
    if not isinstance(value, (bytes, bytearray)) or not value:
        raise InvalidInputError("content is required and must be non-empty bytes")
    return bytes(value)


def _require_policy(value: object) -> dict:
    if not isinstance(value, dict) or not value:
        raise InvalidInputError("resolution_policy is required and must be an object")
    missing = [k for k in POLICY_KEYS if k not in value]
    if missing:
        raise InvalidInputError(
            "resolution_policy is missing required key(s) %s; a partial "
            "policy would be silently completed with defaults" % ", ".join(missing))
    extra = [k for k in value if k not in POLICY_KEYS]
    if extra:
        raise InvalidInputError(
            "resolution_policy has unexpected key(s) %s" % ", ".join(sorted(extra)))
    for key in POLICY_KEYS:
        if not isinstance(value[key], str) or not value[key].strip():
            raise InvalidInputError(
                "resolution_policy key %r must be a non-empty string" % key)
    return value


def _require_terms(value: object) -> dict:
    if not isinstance(value, dict) or not value:
        raise InvalidInputError("agreed_terms is required and must be a non-empty object")
    return value


class WorkWriteService:
    def __init__(self, settings: Settings, client: WriteClient,
                 *, role: str = WORKER_ROLE) -> None:
        self._settings = settings
        self._client = client
        self._role = role

    # -- writes -----------------------------------------------------------

    def submit_proposal(self, work_ref: object, *, scope: object,
                        budget_test_erg: object, eta: object) -> Any:
        ref = require_work_ref(work_ref)
        scope = _require_text(scope, "scope")
        eta = _require_text(eta, "eta")
        if isinstance(budget_test_erg, bool) or not isinstance(budget_test_erg, int) \
                or budget_test_erg <= 0:
            raise InvalidInputError("budget_test_erg must be a positive integer")
        self._require_worker_role()
        projection = self._client.public_projection()
        # Fail closed: only a recognized projection container can
        # establish discovery. Two shapes are recognized:
        #   * live ``crowsnest-public-work-v1``: a list-valued ``items``
        #     whose entries carry the work ref under ``id``;
        #   * legacy: a list-valued ``gigs`` whose entries carry it
        #     under ``work_ref``.
        # A present-but-malformed ``items`` does not fall through to
        # ``gigs``. Any other shape (including ``{}``) authorizes
        # nothing, as does a well-formed shape without the requested ref.
        if not isinstance(projection, dict):
            entries, id_key = None, None
        elif "items" in projection:
            entries, id_key = projection.get("items"), "id"
        else:
            entries, id_key = projection.get("gigs"), "work_ref"
        if not isinstance(entries, list):
            raise WrongStateError(
                "public projection is unrecognized (no list-valued "
                "'items' or 'gigs'); refusing to propose against "
                "undiscovered work")
        if not any(
                isinstance(e, dict) and e.get(id_key) == ref for e in entries):
            raise WrongStateError(
                "work_ref %s is not in the discovered public work; "
                "refusing to propose against undiscovered work" % ref)
        return self._write("submit_proposal", {
            "work_ref": ref, "scope": scope,
            "budget_test_erg": budget_test_erg, "eta": eta})

    def brief_accept(self, work_ref: object, *, note: object = "",
                     expected_state: object = None) -> Any:
        ref = require_work_ref(work_ref)
        # Validate expected_state before actor-store load, signing or
        # any client call (P2-a).
        expected_state = self._validate_expected_state(expected_state)
        if not isinstance(note, str):
            raise InvalidInputError("note must be a string")
        self._require_worker_role()
        terms = self._current_terms(ref)
        self._check_expected_state(terms, expected_state)
        brief = terms.get("brief")
        if not brief:
            raise WrongStateError(
                "no brief is recorded for this work; brief acceptance is "
                "not available in its current state")
        return self._write("brief_accept", {"work_ref": ref, "note": note})

    def consent_terms(self, work_ref: object, *, agreed_terms: object,
                      resolution_policy: object) -> Any:
        ref = require_work_ref(work_ref)
        terms_in = _require_terms(agreed_terms)
        policy = _require_policy(resolution_policy)
        self._require_worker_role()
        terms = self._current_terms(ref)
        current = terms.get("agreed_terms")
        if not isinstance(current, dict) or not current:
            raise WrongStateError(
                "no agreed terms are recorded for this work; there is "
                "nothing to consent to in its current state")
        if current != terms_in:
            raise WrongStateError(
                "agreed_terms do not match the terms currently recorded "
                "for this work; refusing to consent to different terms")
        return self._write("consent_terms", {
            "work_ref": ref, "agreed_terms": terms_in,
            "resolution_policy": policy})

    def attach_artifact(self, work_ref: object, *, media_type: object,
                        content: object) -> Any:
        ref = require_work_ref(work_ref)
        media_type = _require_text(media_type, "media_type")
        data = _require_bytes(content)
        self._require_worker_role()
        self._current_terms(ref)  # state must be readable before a write
        return self._write("attach_artifact", {
            "work_ref": ref, "media_type": media_type,
            "byte_size": len(data),
            "content_sha256": hashlib.sha256(data).hexdigest()})

    def publish_artifact(self, work_ref: object, *, artifact_id: object,
                         content: object, media_type: object = None) -> Any:
        ref = require_work_ref(work_ref)
        artifact_id = _require_text(artifact_id, "artifact_id")
        data = _require_bytes(content)
        if media_type is not None:
            media_type = _require_text(media_type, "media_type")
        self._require_worker_role()
        self._require_known_artifact(ref, artifact_id)
        params: dict[str, Any] = {
            "work_ref": ref, "artifact_id": artifact_id,
            "content_b64": base64.b64encode(data).decode("ascii")}
        if media_type:
            params["media_type"] = media_type
        return self._write("publish_artifact", params)

    def deliver_work(self, work_ref: object, *, artifact_id: object,
                     expected_state: object = None) -> Any:
        ref = require_work_ref(work_ref)
        # Validate expected_state before actor-store load, signing or
        # any client call (P2-a).
        expected_state = self._validate_expected_state(expected_state)
        artifact_id = _require_text(artifact_id, "artifact_id")
        self._require_worker_role()
        terms = self._current_terms(ref)
        self._check_expected_state(terms, expected_state)
        self._require_known_artifact(ref, artifact_id)
        return self._write("deliver_gig", {"work_ref": ref, "artifact_id": artifact_id})

    def deliver_revision(self, work_ref: object, *, media_type: object,
                         content: object) -> Any:
        """Deliver a successor version under the one-revision cap.

        Attaches a NEW artifact (the service issues its id), publishes
        the new bytes under that id and delivers it. The prior version
        stays in history untouched; if attach ever returned an id that
        is already in history, delivery is refused locally rather than
        overwriting it.

        This orchestration is NOT atomic. A FRESH authoritative
        preflight (current terms/state read plus artifact-history read)
        runs before EACH write step; before publish and before deliver
        the new service-issued id must appear in the freshly read
        history (the same membership guard as the standalone
        publish/deliver tools). On a mismatch for a step, that step is
        not dispatched at all. If a later step refuses or its outcome
        is unknown, the error acknowledges the already-completed prior
        steps and the returned artifact_id so reconciliation does not
        restart blindly.
        """
        ref = require_work_ref(work_ref)
        media_type = _require_text(media_type, "media_type")
        data = _require_bytes(content)
        self._require_worker_role()
        # Fresh preflight before the attach write step.
        self._current_terms(ref)
        known = self._known_artifact_ids(ref)
        if not known:
            raise WrongStateError(
                "no prior artifact exists for this work; a revision "
                "requires a first delivered version")
        if len(known) >= MAX_ARTIFACT_VERSIONS:
            raise WrongStateError(
                "one-revision cap reached for this work (%d versions "
                "already in history); refusing another successor" % len(known))
        completed: list[str] = []
        try:
            attached = self._write("attach_artifact", {
                "work_ref": ref, "media_type": media_type,
                "byte_size": len(data),
                "content_sha256": hashlib.sha256(data).hexdigest()})
        except CrowsnestError as exc:
            self._annotate_revision_progress(
                exc, completed=completed, artifact_id=None,
                step="attach_artifact")
            raise
        new_id = attached.get("artifact_id") if isinstance(attached, dict) else None
        if not isinstance(new_id, str) or not new_id.strip():
            # Attach was dispatched and may have committed, but its
            # result is unusable: this is uncertainty, not a pre-write
            # refusal. Whitespace-only and non-string ids are unusable
            # under the same nonblank-text invariant as standalone
            # publish/deliver (_require_text). The original returned
            # token is preserved verbatim as evidence (the bounded
            # diagnostic rendering in the message and the original
            # value unchanged on the artifact_id annotation); it is NOT
            # stripped or repaired into another id, and neither
            # publish nor deliver is dispatched with it.
            # Partial-progress boundary: attach_artifact is the
            # attempted step; publish/deliver were NOT dispatched.
            exc = UncertainWriteError(
                "attach_artifact",
                "attach dispatched but returned no usable artifact_id "
                "(returned artifact_id=%s); "
                "partial progress: attach_artifact may have committed, "
                "publish_artifact and deliver_gig were NOT dispatched, "
                "and no usable artifact_id is known"
                % (_bounded_id_diagnostic(new_id),))
            self._annotate_revision_progress(
                exc, completed=completed, artifact_id=new_id,
                step="attach_artifact")
            raise exc
        completed.append("attach_artifact")
        # Fresh preflight before the publish write step.
        fresh_known = self._revision_preflight(
            ref, step="publish_artifact", completed=completed,
            artifact_id=new_id)
        if new_id in known:
            exc = WrongStateError(
                "attach returned an artifact_id already in history; "
                "refusing to overwrite the prior version")
            self._annotate_revision_progress(
                exc, completed=completed, artifact_id=new_id,
                step="publish_artifact")
            raise exc
        if new_id not in fresh_known:
            exc = WrongStateError(
                "new artifact_id is not in the freshly read artifact "
                "history; refusing to publish an id the service has not "
                "recorded for this work")
            self._annotate_revision_progress(
                exc, completed=completed, artifact_id=new_id,
                step="publish_artifact")
            raise exc
        try:
            self._write("publish_artifact", {
                "work_ref": ref, "artifact_id": new_id,
                "content_b64": base64.b64encode(data).decode("ascii")})
        except CrowsnestError as exc:
            self._annotate_revision_progress(
                exc, completed=completed, artifact_id=new_id,
                step="publish_artifact")
            raise
        completed.append("publish_artifact")
        # Fresh preflight before the deliver write step.
        fresh_known = self._revision_preflight(
            ref, step="deliver_gig", completed=completed,
            artifact_id=new_id)
        if new_id not in fresh_known:
            exc = WrongStateError(
                "new artifact_id is not in the freshly read artifact "
                "history; refusing to deliver an id the service has not "
                "recorded for this work")
            self._annotate_revision_progress(
                exc, completed=completed, artifact_id=new_id,
                step="deliver_gig")
            raise exc
        try:
            delivered = self._write(
                "deliver_gig", {"work_ref": ref, "artifact_id": new_id})
        except CrowsnestError as exc:
            self._annotate_revision_progress(
                exc, completed=completed, artifact_id=new_id,
                step="deliver_gig")
            raise
        if isinstance(delivered, dict):
            return {**delivered, "artifact_id": new_id}
        return {"artifact_id": new_id, "result": delivered}

    def _revision_preflight(self, ref: str, *, step: str,
                            completed: list, artifact_id) -> list:
        """Fresh terms/state + history read before one revision step.

        Any failure here means zero dispatch for ``step``; the error is
        annotated with the steps already completed so prior progress is
        never hidden behind a fresh-start assumption.
        """
        try:
            self._current_terms(ref)
            return self._known_artifact_ids(ref)
        except CrowsnestError as exc:
            self._annotate_revision_progress(
                exc, completed=completed, artifact_id=artifact_id,
                step=step)
            raise

    @staticmethod
    def _annotate_revision_progress(exc: CrowsnestError, *, completed,
                                    artifact_id, step: str) -> None:
        """Expose revision partial progress on an error, in place.

        Sets ``completed_steps`` / ``artifact_id`` / ``revision_step``
        attributes and appends the same facts to the message, so both
        programmatic callers and the MCP ToolError text acknowledge
        already-completed steps. The exception type (and any native
        status) is preserved: known refusals stay known.
        """
        completed = list(completed)
        exc.completed_steps = completed
        # Original value preserved unchanged for evidence -- it may be
        # a deliberately preserved malformed (non-str) upstream token.
        # Only its rendering in the note below is bounded.
        exc.artifact_id = artifact_id
        exc.revision_step = step
        note = (
            "revision partial progress: completed_steps=%r, "
            "artifact_id=%s, step=%r; this orchestration is not atomic "
            "-- do not restart blindly; reconcile via inspect_terms "
            "and inspect_history first"
            % (completed, _bounded_id_diagnostic(artifact_id), step))
        if note not in str(exc):
            exc.args = ("%s; %s" % (exc, note),) if exc.args else (note,)

    # -- guards / plumbing --------------------------------------------------

    def _require_worker_role(self) -> None:
        if self._role != WORKER_ROLE:
            raise WrongRoleError(
                "this write surface is worker-only; the configured role "
                "is not %r" % WORKER_ROLE)

    def _current_terms(self, ref: str) -> dict:
        result = self._read("get_gig", {"work_ref": ref})
        if not isinstance(result, dict):
            raise WrongStateError("current terms/state for this work are unreadable")
        state = result.get("state")
        if not isinstance(state, str) or not state:
            raise WrongStateError(
                "current state for this work is unavailable; reconcile "
                "via inspect_terms before writing")
        return result

    @staticmethod
    def _validate_expected_state(expected_state: object):
        """Local shape check for the optional expectation.

        Purely local: no store load, signing or client call may happen
        before this has passed.
        """
        if expected_state is None:
            return None
        if not isinstance(expected_state, str) or not expected_state.strip():
            raise InvalidInputError("expected_state must be a non-empty string")
        return expected_state

    @classmethod
    def _check_expected_state(cls, terms: dict, expected_state: object) -> None:
        expected_state = cls._validate_expected_state(expected_state)
        if expected_state is None:
            return
        actual = terms.get("state")
        if actual != expected_state:
            raise WrongStateError(
                "current state is %r, not the expected %r; refusing "
                "this write (reconcile via inspect_terms)"
                % (actual, expected_state))

    def _known_artifact_ids(self, ref: str) -> list:
        history = self._read("artifact_history", {"work_ref": ref})
        if not isinstance(history, list):
            raise WrongStateError("artifact history for this work is unreadable")
        ids = []
        for entry in history:
            if isinstance(entry, dict) and isinstance(entry.get("artifact_id"), str):
                if entry["artifact_id"] not in ids:
                    ids.append(entry["artifact_id"])
        return ids

    def _require_known_artifact(self, ref: str, artifact_id: str) -> None:
        if artifact_id not in self._known_artifact_ids(ref):
            raise WrongStateError(
                "artifact_id %s is not in this work's artifact history; "
                "refusing to use an id the service did not issue for "
                "this work" % artifact_id)

    def _envelope(self, action: str, params: dict) -> dict:
        store_path, account_id = self._settings.require_actor()
        identity = load_actor_store(store_path)
        return identity.action_envelope(account_id, self._role, action, params)

    def _read(self, action: str, params: dict) -> Any:
        return self._client.signed_action(action, self._envelope(action, params))

    def _write(self, action: str, params: dict) -> Any:
        envelope = self._envelope(action, params)
        try:
            return self._client.signed_write_action(action, envelope)
        except (ServiceRefusalError, UncertainWriteError):
            raise
        except TransportError as exc:
            raise UncertainWriteError(action, str(exc)) from exc


__all__ = ["WorkWriteService", "WriteClient", "POLICY_KEYS", "MAX_ARTIFACT_VERSIONS"]
