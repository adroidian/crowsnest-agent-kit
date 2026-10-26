"""Read-only work service: the logic behind the MCP tools.

Mapping to the supported participant surface (participant 0.3.2):

* ``discover_work``   -> public projection (``crowsnest-participant
  discover``; the mounted ``GET /v1/public/projection`` route)
* ``list_my_gigs``    -> signed action ``my_gigs`` (``my-gigs`` CLI command)
* ``inspect_terms``   -> signed action ``get_gig`` keyed only by the public
  ``work_ref`` (``crowsnest-worker terms``; returns the sanitized view:
  work_ref, state, brief, agreed terms, resolution policy -- no gig_id)
* ``inspect_history`` -> signed action ``artifact_history`` keyed only by
  ``work_ref`` (``crowsnest-worker history``; own artifact/review history,
  which also reflects current state transitions)

Every signed read validates its reference locally first, then binds the
configured actor store (never a tool-supplied path), then dispatches
exactly one signed request. There is no write path in this module.
"""
from __future__ import annotations

from typing import Any, Protocol

from .config import WORKER_ROLE, Settings
from .errors import InvalidReferenceError
from .identity import load_actor_store
from .validation import require_work_ref


class ReadClient(Protocol):
    def public_projection(self) -> Any: ...

    def signed_action(self, action: str, envelope: dict) -> Any: ...


class WorkReadService:
    def __init__(self, settings: Settings, client: ReadClient) -> None:
        self._settings = settings
        self._client = client

    def discover_work(self) -> Any:
        """Public discovery over the mounted projection route."""
        return self._client.public_projection()

    def list_my_gigs(self) -> Any:
        """The configured actor's own gigs (signed ``my_gigs`` read)."""
        return self._signed("my_gigs", {})

    def inspect_terms(self, work_ref: object) -> Any:
        """Agreed terms + current sanitized state for one work_ref."""
        ref = require_work_ref(work_ref)
        return self._signed("get_gig", {"work_ref": ref})

    def inspect_history(self, work_ref: object) -> Any:
        """Own artifact and review history for one work_ref."""
        ref = require_work_ref(work_ref)
        return self._signed("artifact_history", {"work_ref": ref})

    def _signed(self, action: str, params: dict) -> Any:
        # Configuration and store are bound here, from the environment,
        # after any reference validation done by the caller. The store
        # is loaded per call so a rotated/repaired store is picked up
        # and so list_tools never needs credentials.
        store_path, account_id = self._settings.require_actor()
        identity = load_actor_store(store_path)
        envelope = identity.action_envelope(
            account_id, WORKER_ROLE, action, params
        )
        return self._client.signed_action(action, envelope)


__all__ = ["WorkReadService", "ReadClient", "InvalidReferenceError"]
