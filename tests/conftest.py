"""Offline fixture: a participant-shaped actor store generated locally.

The signing key is generated fresh in the fixture. Nothing here connects
to a network, and the store written under tmp_path is a test artifact,
not a real actor's credential.
"""
from __future__ import annotations

import base64
import hashlib
import json

import pytest
from nacl.signing import SigningKey


@pytest.fixture()
def actor_store(tmp_path):
    signing_key = SigningKey.generate()
    public_bytes = bytes(signing_key.verify_key)
    payload = {
        "version": 1,
        "principal_id": "p_" + hashlib.sha256(public_bytes).hexdigest()[:24],
        "display_name": "lantern-test-worker",
        "public_key": base64.b64encode(public_bytes).decode("ascii"),
        "signing_key_b64": base64.b64encode(bytes(signing_key)).decode("ascii"),
    }
    path = tmp_path / "identity.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path), payload["principal_id"]


class RecordingClient:
    """Fake read client: records calls, returns canned offline fixtures."""

    def __init__(self, projection=None, signed=None):
        self.calls = []
        self._projection = projection if projection is not None else {"gigs": []}
        self._signed = signed if signed is not None else {}

    def public_projection(self):
        self.calls.append(("projection",))
        return self._projection

    def signed_action(self, action, envelope):
        self.calls.append(("signed", action, envelope))
        return self._signed


@pytest.fixture()
def recording_client():
    return RecordingClient()
