#!/usr/bin/env python3
"""Real MCP client probe: initialize + tools/list against the stdio server.

Launches the installed ``crowsnest-muse-worker`` console script over
stdio, performs a real MCP initialize handshake, lists tools, and also
calls ``inspect_terms`` with a deliberately malformed work_ref to show
that invalid references fail as typed tool errors before any dispatch
(this environment normally has no actor store configured, and validation
must fire before the store is even consulted). The probe asserts the
exact tool set and that the malformed-reference error contains the
expected category/detail, exiting nonzero on any mismatch.

This proves the MCP protocol surface offline. It does NOT prove a live
Crowsnest service round trip.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


EXPECTED_TOOLS = {
    "discover_work",
    "list_my_gigs",
    "inspect_terms",
    "inspect_history",
    # Task 2 worker write tools
    "submit_proposal",
    "brief_accept",
    "consent_terms",
    "attach_artifact",
    "publish_artifact",
    "deliver_work",
    "deliver_revision",
}
EXPECTED_BAD_REF_CATEGORY = "InvalidReferenceError"
EXPECTED_BAD_REF_DETAIL = (
    "work_ref must be 'work_' followed by exactly 16 lowercase hex characters"
)


async def run() -> int:
    failures = []

    def check(condition: bool, label: str) -> None:
        print("%s: %s" % ("PASS" if condition else "FAIL", label))
        if not condition:
            failures.append(label)

    server_command = os.environ.get(
        "CROWSNEST_MUSE_WORKER_CMD", "crowsnest-muse-worker"
    )
    params = StdioServerParameters(command=server_command, args=[])
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
            print("initialize: server=%s version=%s protocol=%s" % (
                init.server_info.name,
                init.server_info.version,
                init.protocol_version,
            ))
            tools = await session.list_tools()
            actual_tools = {tool.name for tool in tools.tools}
            check(
                actual_tools == EXPECTED_TOOLS,
                "exact tool set %s (got %s)"
                % (sorted(EXPECTED_TOOLS), sorted(actual_tools)),
            )
            print("list_tools:")
            print(json.dumps(
                [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.input_schema,
                    }
                    for tool in tools.tools
                ],
                indent=2,
                sort_keys=True,
            ))
            bad = await session.call_tool(
                "inspect_terms", {"work_ref": "not-a-work-ref"}
            )
            print("inspect_terms(malformed work_ref) isError=%s" % bad.is_error)
            print("inspect_terms(malformed work_ref) content:")
            bad_text = ""
            for item in bad.content:
                text = getattr(item, "text", item)
                print(text)
                bad_text += str(text)
            check(bool(bad.is_error), "malformed work_ref returns isError")
            check(
                EXPECTED_BAD_REF_CATEGORY in bad_text,
                "malformed work_ref error contains category %s"
                % EXPECTED_BAD_REF_CATEGORY,
            )
            check(
                EXPECTED_BAD_REF_DETAIL in bad_text,
                "malformed work_ref error contains detail %r"
                % EXPECTED_BAD_REF_DETAIL,
            )
    if failures:
        print("probe: FAILED (%d check(s))" % len(failures))
        return 1
    print("probe: OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
