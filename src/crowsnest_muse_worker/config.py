"""Adapter configuration, taken only from the environment.

Tool input can never override any of this: in particular the actor store
path (``CROWSNEST_STORE``) and the account id (``CROWSNEST_ACCOUNT_ID``)
are bound here, at server configuration time, so a tool caller cannot
point the server at an arbitrary key file.
"""
from __future__ import annotations

import math
import os
import socket
from dataclasses import dataclass
from typing import Mapping, Optional

from .errors import ConfigurationError

DEFAULT_BASE_URL = "https://crowsnest.kasnet.us/api"

# This increment is the worker read surface; the role is not tool input.
WORKER_ROLE = "worker"


def validate_timeout_seconds(value, *, name: str = "timeout") -> float:
    """Return ``value`` as a finite, positive, platform-usable timeout.

    ``nan``/``inf`` pass a naive ``<= 0`` check but fail later inside the
    socket layer as untyped ``ValueError``/``OverflowError``.  Finite but
    enormous values can likewise exceed what the platform ``time_t`` /
    socket-timeout conversion can represent.  Probe the actual platform
    conversion once (a local socket object; nothing is connected) so
    every such failure is raised here as a ``ConfigurationError``.

    ``name`` is the configuration label used in the error message; the
    offending value itself is never echoed.
    """
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        raise ConfigurationError(
            "%s must be a positive number" % name
        ) from None
    if not math.isfinite(timeout) or timeout <= 0:
        raise ConfigurationError(
            "%s must be a positive number (finite)" % name
        )
    probe = None
    try:
        probe = socket.socket()
        probe.settimeout(timeout)
    except (OverflowError, ValueError, OSError):
        raise ConfigurationError(
            "%s must be a positive number the platform can represent"
            % name
        ) from None
    finally:
        if probe is not None:
            probe.close()
    return timeout


@dataclass(frozen=True)
class Settings:
    base_url: str = DEFAULT_BASE_URL
    store_path: Optional[str] = None
    account_id: Optional[str] = None
    timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        # Direct construction is held to the same boundary as from_env,
        # so a non-finite/unrepresentable timeout can never be stored.
        object.__setattr__(
            self,
            "timeout_seconds",
            validate_timeout_seconds(
                self.timeout_seconds, name="CROWSNEST_TIMEOUT_SECONDS"
            ),
        )

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        source = os.environ if env is None else env
        raw_timeout = source.get("CROWSNEST_TIMEOUT_SECONDS", "15")
        try:
            timeout = float(raw_timeout)
        except (TypeError, ValueError):
            raise ConfigurationError(
                "CROWSNEST_TIMEOUT_SECONDS must be a positive number"
            ) from None
        # Finite/positive/platform-representable checks (incl. the
        # socket-conversion probe) run in __post_init__ via
        # validate_timeout_seconds and raise ConfigurationError.
        base_url = source.get("CROWSNEST_BASE_URL", DEFAULT_BASE_URL).strip()
        if not base_url:
            raise ConfigurationError("CROWSNEST_BASE_URL must not be empty")
        return cls(
            base_url=base_url,
            store_path=source.get("CROWSNEST_STORE") or None,
            account_id=source.get("CROWSNEST_ACCOUNT_ID") or None,
            timeout_seconds=timeout,
        )

    def require_actor(self) -> tuple[str, str]:
        """Return (store_path, account_id) or raise before any I/O."""
        if not self.store_path:
            raise ConfigurationError(
                "CROWSNEST_STORE is not configured; signed reads are "
                "unavailable (public discovery does not need it)"
            )
        if not self.account_id:
            raise ConfigurationError(
                "CROWSNEST_ACCOUNT_ID is not configured; signed reads are "
                "unavailable"
            )
        return self.store_path, self.account_id
