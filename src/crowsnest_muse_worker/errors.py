"""Typed errors for the Crowsnest MCP adapter (eleven tools).

The adapter exposes four read tools and seven worker-only write tools
(eleven in total; offline-proven, with no live-service claim made here).
Every failure raised before or during a read or write is one of these
types, so an MCP caller (and the tests) can distinguish a bad local
reference from a configuration problem, a transport problem and a
service refusal.
Locally generated messages never include key material. Upstream
response text is untrusted: it is included only as a bounded diagnostic
(see ``client.MAX_ERROR_DETAIL_CHARS``), never as trusted content.
"""
from __future__ import annotations

from typing import Any


class CrowsnestError(Exception):
    """Base class for all adapter errors.

    Revision partial-progress attributes: ``None``/empty for ordinary
    single-step errors; the revision orchestrator annotates errors it
    raises after some steps may have completed (see write_service).

    These are instance-local (initialized per instance in ``__init__``),
    never a shared mutable class default: mutating one error's
    ``completed_steps`` cannot affect any other error. ``artifact_id``
    may hold a deliberately preserved malformed upstream value, so it
    is not restricted to ``str``.
    """

    completed_steps: list[str]
    artifact_id: Any
    revision_step: str | None

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.completed_steps = []
        self.artifact_id = None
        self.revision_step = None


class ConfigurationError(CrowsnestError):
    """Required environment/config is missing or malformed.

    Raised before any key store is opened and before any network call.
    """


class InvalidReferenceError(CrowsnestError, ValueError):
    """A tool-supplied reference (e.g. work_ref) is malformed.

    Raised before the actor store is loaded and before anything is signed
    or dispatched, mirroring the participant worker CLI's local check.
    """


class ActorStoreError(CrowsnestError):
    """The configured actor store is missing, unreadable or inconsistent.

    The store path comes only from configuration; tool input can never
    select it, so this error never names a tool-supplied path.
    """


class TransportError(CrowsnestError):
    """No usable result was obtained from the service.

    Covers connection failure and a 2xx response whose body is empty,
    not JSON, or the wrong shape. A status header alone is not treated
    as knowledge of a result.
    """


class ServiceRefusalError(CrowsnestError):
    """The service answered with a non-2xx status; ``status`` is native."""

    def __init__(self, message: str, *, status: int) -> None:
        super().__init__(message)
        self.status = status


class InvalidInputError(CrowsnestError, ValueError):
    """A tool-supplied write input is malformed (scope, policy, bytes...).

    Raised locally, before the actor store is loaded and before any
    signing or dispatch.
    """


class WrongStateError(CrowsnestError):
    """Current state (from a Task-1 read) does not permit this write.

    For a standalone write this is raised after the pre-flight read but
    before any write dispatch: the write action is never sent. In the
    multi-step revision orchestration a known later-step refusal keeps
    this classification, but the error then carries ``completed_steps``
    / ``artifact_id`` / ``revision_step`` and says so in its message --
    prior steps may already have committed and must be acknowledged,
    never treated as if nothing was dispatched. State values are
    whatever the service actually returned; this adapter invents no
    state names.
    """


class WrongRoleError(CrowsnestError):
    """The configured role is not the worker role for this write surface.

    Raised locally before the actor store is loaded or anything is
    dispatched. Tool input can never select a role.
    """


class UncertainWriteError(CrowsnestError):
    """A write was dispatched but no usable result was obtained.

    The outcome is UNKNOWN: the write may or may not have committed.
    It was NOT retried and NOT re-signed. The caller must reconcile
    with inspect_terms / inspect_history (signed Task-1 reads) before
    deciding what to do next.
    """

    def __init__(self, action: str, detail: str = "") -> None:
        message = (
            "%s: write dispatched but outcome is UNKNOWN (%s). "
            "It was NOT retried and NOT re-signed; never claim success. "
            "Reconcile first via inspect_terms and inspect_history "
            "reads, then decide." % (action, detail or "no usable result")
        )
        super().__init__(message)
        self.action = action
