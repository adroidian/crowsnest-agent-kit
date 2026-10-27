"""Loading the configured actor's own Ed25519 store and signing reads.

Interoperability notes (wire contract measured from participant 0.3.2,
not code copied from it):

* the local store is a JSON object with ``version: 1``, ``principal_id``,
  ``display_name``, ``public_key`` (base64) and ``signing_key_b64``
  (base64, 32-byte Ed25519 seed);
* ``principal_id`` is ``"p_" + sha256(public_key_bytes).hexdigest()[:24]``;
* a signed action envelope is ``{"body": body, "sig": sig}`` where ``sig``
  is the base64 Ed25519 signature over the canonical body bytes
  (``json.dumps(body, sort_keys=True, separators=(",", ":"))``), and the
  body carries a fresh random nonce per call.

The private key never leaves this module: it is not returned by any
function, not logged, and not included in any exception message.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid

from nacl.signing import SigningKey

from .errors import ActorStoreError

STORE_VERSION = 1


def _canonical(body: dict) -> bytes:
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _principal_id_for(public_key_bytes: bytes) -> str:
    return "p_" + hashlib.sha256(public_key_bytes).hexdigest()[:24]


class ActorIdentity:
    """The configured participant's own identity (key kept private)."""

    def __init__(self, principal_id: str, display_name: str,
                 public_key_b64: str, signing_key: SigningKey) -> None:
        self.principal_id = principal_id
        self.display_name = display_name
        self.public_key_b64 = public_key_b64
        self._signing_key = signing_key

    def __repr__(self) -> str:  # never leak key material
        return "<ActorIdentity %s %s>" % (self.principal_id, self.display_name)

    __str__ = __repr__

    def action_envelope(self, account_id: str, role: str, action: str,
                        params: dict) -> dict:
        """Build one freshly-signed action envelope for a single call."""
        body = {
            "type": "action",
            "principal_id": self.principal_id,
            "account_id": account_id,
            "role": role,
            "action": action,
            "params": params,
            "nonce": uuid.uuid4().hex + uuid.uuid4().hex,
        }
        signature = self._signing_key.sign(_canonical(body)).signature
        return {"body": body, "sig": base64.b64encode(signature).decode("ascii")}


def load_actor_store(path: str) -> ActorIdentity:
    """Load and consistency-check the store at the configured path.

    Raises ActorStoreError for a missing file, bad JSON, an unsupported
    version, a malformed key, or a store whose public key / principal id
    do not match the stored signing key.
    """
    if not os.path.isfile(path):
        raise ActorStoreError(
            "no actor store at the configured CROWSNEST_STORE path; "
            "create the participant identity with the participant client"
        )
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ActorStoreError("actor store is unreadable or not JSON") from exc
    if not isinstance(payload, dict) or payload.get("version") != STORE_VERSION:
        raise ActorStoreError("unsupported actor store version")
    try:
        seed = base64.b64decode(
            str(payload["signing_key_b64"]).encode("ascii"), validate=True
        )
        stored_public = str(payload["public_key"])
        stored_principal = str(payload["principal_id"])
        display_name = str(payload["display_name"])
    except (KeyError, ValueError) as exc:
        raise ActorStoreError("actor store is missing required fields") from exc
    if len(seed) != 32:
        raise ActorStoreError("actor store signing key is not 32 bytes")
    signing_key = SigningKey(seed)
    public_bytes = bytes(signing_key.verify_key)
    if base64.b64encode(public_bytes).decode("ascii") != stored_public:
        raise ActorStoreError(
            "actor store is inconsistent: public key does not match key"
        )
    if _principal_id_for(public_bytes) != stored_principal:
        raise ActorStoreError(
            "actor store is inconsistent: principal_id does not match key"
        )
    return ActorIdentity(stored_principal, display_name, stored_public,
                         signing_key)
