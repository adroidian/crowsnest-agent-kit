"""Real stdio protocol tests: typed errors must survive the MCP boundary.

These spawn the actual server as a subprocess and talk to it with a
real MCP ``ClientSession`` over stdio. They assert the error CATEGORY
and message content visible to the client, not only ``is_error`` --
the regression covered here is MCP 2.3.0 masking unexpected
exceptions as a generic ``Error executing tool <name>`` crash.

Offline only: no live Crowsnest service is contacted. Malformed
references and missing/invalid configuration fail locally before any
signing or dispatch.
"""
from __future__ import annotations

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# Every adapter configuration variable. The subprocess environment is
# hermetic with respect to all of these: each is stripped from the
# inherited environment, a valid loopback-only base URL and a known
# timeout are supplied, and per-test overrides are applied explicitly.
ADAPTER_ENV_VARS = (
    "CROWSNEST_BASE_URL",
    "CROWSNEST_STORE",
    "CROWSNEST_ACCOUNT_ID",
    "CROWSNEST_TIMEOUT_SECONDS",
)

# Bounded deadline for a whole subprocess protocol session, so a
# protocol regression fails instead of hanging CI indefinitely.
PROTOCOL_TIMEOUT_SECONDS = 30.0


def _env(**overrides):
    env = dict(os.environ)
    for key in ADAPTER_ENV_VARS:
        env.pop(key, None)
    env["CROWSNEST_BASE_URL"] = "http://127.0.0.1:9/api"
    env["CROWSNEST_TIMEOUT_SECONDS"] = "5"
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


async def _session_call(env, tool, arguments):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "crowsnest_muse_worker"],
        env=env,
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await session.call_tool(tool, arguments)


async def _call_tool(env, tool, arguments):
    return await asyncio.wait_for(
        _session_call(env, tool, arguments),
        timeout=PROTOCOL_TIMEOUT_SECONDS,
    )


def _text(result) -> str:
    return "\n".join(
        str(getattr(item, "text", item)) for item in result.content
    )


def test_protocol_malformed_work_ref_preserves_typed_error():
    result = asyncio.run(
        _call_tool(_env(), "inspect_terms", {"work_ref": "not-a-work-ref"})
    )
    assert result.is_error
    text = _text(result)
    assert "InvalidReferenceError" in text
    assert (
        "work_ref must be 'work_' followed by exactly 16 lowercase "
        "hex characters" in text
    )
    # Not the SDK's generic crash mask.
    assert text != "Error executing tool inspect_terms"


def test_protocol_missing_configuration_preserves_typed_error():
    # No CROWSNEST_STORE / CROWSNEST_ACCOUNT_ID: signed read must reach
    # the client as ConfigurationError, not a generic crash.
    result = asyncio.run(_call_tool(_env(), "list_my_gigs", {}))
    assert result.is_error
    text = _text(result)
    assert "ConfigurationError" in text
    assert "CROWSNEST_STORE is not configured" in text
    assert text != "Error executing tool list_my_gigs"


def test_protocol_construction_configuration_error_preserves_typed_error():
    # Invalid timeout makes Settings.from_env() raise ConfigurationError
    # during _service() construction, which previously ran outside the
    # error-conversion wrapper. It must still reach the client typed.
    result = asyncio.run(
        _call_tool(
            _env(CROWSNEST_TIMEOUT_SECONDS="nope"), "list_my_gigs", {}
        )
    )
    assert result.is_error
    text = _text(result)
    assert "ConfigurationError" in text
    assert "CROWSNEST_TIMEOUT_SECONDS must be a positive number" in text
    assert text != "Error executing tool list_my_gigs"


def test_protocol_nonfinite_timeout_preserves_typed_error():
    # I1 regression (real stdio): nan passes a naive <= 0 check but must
    # be rejected at configuration time as ConfigurationError.
    result = asyncio.run(
        _call_tool(
            _env(CROWSNEST_TIMEOUT_SECONDS="nan"), "list_my_gigs", {}
        )
    )
    assert result.is_error
    text = _text(result)
    assert "ConfigurationError" in text
    assert "CROWSNEST_TIMEOUT_SECONDS must be a positive number" in text


def test_protocol_unrepresentable_timeout_preserves_typed_error():
    # Finite but far beyond what the platform socket timeout can hold.
    result = asyncio.run(
        _call_tool(
            _env(CROWSNEST_TIMEOUT_SECONDS="1e308"), "list_my_gigs", {}
        )
    )
    assert result.is_error
    text = _text(result)
    assert "ConfigurationError" in text
    assert "CROWSNEST_TIMEOUT_SECONDS must be a positive number" in text


def test_protocol_malformed_base_url_preserves_typed_error_without_echo():
    # I1 regression (real stdio): a port that cannot be cast raises
    # ValueError from parsed.port in the stdlib. It must surface as
    # ConfigurationError, and the supplied URL -- including its embedded
    # credential -- must not be echoed to the MCP caller.
    secret = "probe-secret-not-to-echo"
    result = asyncio.run(
        _call_tool(
            _env(
                CROWSNEST_BASE_URL=(
                    "http://user:%s@localhost:bogus/api" % secret
                )
            ),
            "list_my_gigs",
            {},
        )
    )
    assert result.is_error
    text = _text(result)
    assert "ConfigurationError" in text
    assert "base URL" in text
    assert secret not in text
    assert "localhost:bogus" not in text
