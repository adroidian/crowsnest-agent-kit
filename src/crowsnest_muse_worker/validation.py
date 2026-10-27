"""Reference validation, performed locally before any dispatch."""
from __future__ import annotations

import re

from .errors import InvalidReferenceError

# Public work reference exactly as the service issues it (measured from
# crowsnest_participant.worker in participant 0.3.2): the literal prefix
# ``work_`` followed by exactly 16 lowercase hex characters.
_WORK_REF_RE = re.compile(r"work_[0-9a-f]{16}")


def require_work_ref(value: object) -> str:
    """Return ``value`` if it is a well-formed work_ref, else raise.

    This runs before the actor store is loaded, before anything is
    signed and before any request is dispatched.
    """
    if not isinstance(value, str) or not value:
        raise InvalidReferenceError("work_ref is required and must be a string")
    if _WORK_REF_RE.fullmatch(value) is None:
        raise InvalidReferenceError(
            "work_ref must be 'work_' followed by exactly 16 lowercase "
            "hex characters"
        )
    return value
